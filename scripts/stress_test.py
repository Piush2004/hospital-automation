"""Concurrency/load stress test against the running backend (websocket
channel). Two things this specifically checks:

1. **Race-condition correctness**: many patients concurrently competing
   for the same doctor's slots — does the app ever double-book a
   (doctor_id, slot_start) pair? This is the highest-value check: it's a
   real correctness question, not just a load number.
2. **Broad concurrent load**: N simultaneous full booking flows across
   different departments, checking success rate and latency.

Requires the backend running on :8000 (see README). Does not require
Ollama to be fast - LLM triage calls will naturally serialize somewhat
depending on Ollama's concurrency settings; this test measures wall-clock
under whatever the real local setup provides, not synthetic throughput.

Usage (from backend/, with the venv active):
    .venv/Scripts/python ../scripts/stress_test.py
"""

import asyncio
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import websockets

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

WS_URL = "ws://127.0.0.1:8000/ws/chat"


async def run_booking_flow(phone: str, name: str, symptom: str, slot_choice: str = "1") -> dict:
    """Drives one patient through name -> symptom -> pick-a-slot. Returns a
    result dict with timing + outcome, never raises (stress tests should
    keep going and report failures, not crash the harness).
    """
    result = {"phone": phone, "ok": False, "error": None, "appointment_ref": None, "elapsed": None}
    start = time.monotonic()
    try:
        uri = f"{WS_URL}?phone={phone.replace('+', '%2B')}"
        async with websockets.connect(uri, open_timeout=10, close_timeout=5) as ws:
            greeting = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))

            if "name" in greeting["content"].lower():
                await ws.send(name)
                await asyncio.wait_for(ws.recv(), timeout=30)

            await ws.send(symptom)
            triage_reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))

            if "reply with a number" not in triage_reply["content"].lower():
                result["error"] = f"unexpected reply after symptom: {triage_reply['content'][:200]}"
                return result

            await ws.send(slot_choice)
            booking_reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            content = booking_reply["content"]

            match = re.search(r"booked with (.+?) on (.+? UTC)", content)
            if match:
                result["appointment_ref"] = (match.group(1), match.group(2))
                result["ok"] = True
            else:
                result["error"] = f"couldn't confirm booking from reply: {content[:200]}"
    except Exception as exc:  # noqa: BLE001 - stress test: capture everything
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["elapsed"] = round(time.monotonic() - start, 2)
    return result


async def race_condition_test(concurrency: int = 8) -> list[dict]:
    """All patients report the same symptom (Dermatology has exactly one
    seeded doctor - Dr. Sameer Khan) and all pick slot #1. If there's a
    TOCTOU race in book_appointment, several of these should land on the
    identical (doctor, slot_start) pair.
    """
    print(f"\n=== Race-condition test: {concurrency} patients competing for the same slot ===")
    tasks = [
        run_booking_flow(f"+9199990001{i:02d}", f"RaceTest{i}", "I have a persistent itchy skin rash", "1")
        for i in range(concurrency)
    ]
    results = await asyncio.gather(*tasks)
    for r in results:
        status = "OK " if r["ok"] else "FAIL"
        print(f"  [{status}] {r['phone']} ({r['elapsed']}s) -> {r['appointment_ref'] or r['error']}")
    return results


async def load_test(concurrency: int = 15) -> list[dict]:
    """Broader concurrent load: different symptoms, different departments,
    all firing at once.
    """
    print(f"\n=== Load test: {concurrency} concurrent full booking flows ===")
    symptoms = [
        "I have a bad ear infection",
        "chronic back pain after lifting something heavy",
        "my child has a fever and cough",
        "persistent chest tightness",
        "a rash that won't go away",
        "joint pain in my knee",
        "sore throat and blocked ears",
        "general checkup, feeling unwell",
    ]
    tasks = [
        run_booking_flow(f"+9199990002{i:02d}", f"LoadTest{i}", symptoms[i % len(symptoms)], "1")
        for i in range(concurrency)
    ]
    start = time.monotonic()
    results = await asyncio.gather(*tasks)
    total_elapsed = round(time.monotonic() - start, 2)

    ok_count = sum(1 for r in results if r["ok"])
    print(f"  {ok_count}/{concurrency} succeeded in {total_elapsed}s wall-clock")
    latencies = sorted(r["elapsed"] for r in results if r["ok"])
    if latencies:
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]
        print(f"  latency: min={latencies[0]}s p50={p50}s p95={p95}s max={latencies[-1]}s")
    for r in results:
        if not r["ok"]:
            print(f"  [FAIL] {r['phone']}: {r['error']}")
    return results


def check_db_integrity() -> bool:
    """Scans the real DB for duplicate active (doctor_id, slot_start)
    pairs - the actual correctness check the race-condition test above is
    trying to trigger. Returns True if clean.
    """
    from app.db import SessionLocal
    from app.models import Appointment, Payment
    from app.services.doctors import ACTIVE_STATUSES

    print("\n=== DB integrity check ===")
    db = SessionLocal()
    try:
        rows = (
            db.query(Appointment.doctor_id, Appointment.slot_start, Appointment.id)
            .filter(Appointment.status.in_(ACTIVE_STATUSES))
            .all()
        )
        seen = Counter((doctor_id, slot_start) for doctor_id, slot_start, _id in rows)
        duplicates = {k: v for k, v in seen.items() if v > 1}

        if duplicates:
            print(f"  DOUBLE-BOOKING DETECTED: {len(duplicates)} slot(s) booked more than once:")
            for (doctor_id, slot_start), count in duplicates.items():
                dupe_ids = [a_id for d_id, s_start, a_id in rows if d_id == doctor_id and s_start == slot_start]
                print(f"    doctor_id={doctor_id} slot_start={slot_start}: {count}x (appointment ids {dupe_ids})")
        else:
            print(f"  OK: no double-bookings across {len(rows)} active appointments.")

        # Payment 1:1 sanity check.
        appt_ids = [a_id for _d, _s, a_id in rows]
        payment_appt_ids = [p.appointment_id for p in db.query(Payment).all()]
        payment_dupes = {k: v for k, v in Counter(payment_appt_ids).items() if v > 1}
        if payment_dupes:
            print(f"  PAYMENT INTEGRITY ISSUE: appointments with >1 payment row: {payment_dupes}")
        else:
            print(f"  OK: {len(payment_appt_ids)} payment rows, all 1:1 with appointments.")

        return not duplicates and not payment_dupes
    finally:
        db.close()


def cleanup_test_data() -> None:
    from app.db import SessionLocal
    from app.models import Appointment, AuditLog, ConversationSession, Patient, Payment

    db = SessionLocal()
    try:
        test_patients = db.query(Patient).filter(Patient.phone.like("+919999%")).all()
        patient_ids = [p.id for p in test_patients]
        if patient_ids:
            appt_ids = [a.id for a in db.query(Appointment).filter(Appointment.patient_id.in_(patient_ids)).all()]
            payment_ids = [p.id for p in db.query(Payment).filter(Payment.appointment_id.in_(appt_ids)).all()]
            db.query(AuditLog).filter(
                AuditLog.entity_type == "Appointment", AuditLog.entity_id.in_([str(i) for i in appt_ids])
            ).delete(synchronize_session=False)
            db.query(AuditLog).filter(
                AuditLog.entity_type == "Payment", AuditLog.entity_id.in_([str(i) for i in payment_ids])
            ).delete(synchronize_session=False)
            db.query(Payment).filter(Payment.appointment_id.in_(appt_ids)).delete(synchronize_session=False)
            db.query(Appointment).filter(Appointment.patient_id.in_(patient_ids)).delete(synchronize_session=False)
            db.query(ConversationSession).filter(ConversationSession.patient_id.in_(patient_ids)).delete(
                synchronize_session=False
            )
            db.query(Patient).filter(Patient.id.in_(patient_ids)).delete(synchronize_session=False)
            db.commit()
            print(f"\n[cleanup] Removed {len(patient_ids)} stress-test patients and their data.")
    finally:
        db.close()


async def main() -> None:
    race_results = await race_condition_test(concurrency=8)
    load_results = await load_test(concurrency=15)
    integrity_ok = check_db_integrity()

    race_ok = sum(1 for r in race_results if r["ok"])
    load_ok = sum(1 for r in load_results if r["ok"])

    print("\n=== Summary ===")
    print(f"  Race test: {race_ok}/{len(race_results)} completed bookings")
    print(f"  Load test: {load_ok}/{len(load_results)} completed bookings")
    print(f"  DB integrity: {'PASS' if integrity_ok else 'FAIL'}")

    passed = integrity_ok and race_ok >= 1 and load_ok >= len(load_results) * 0.8
    print(f"\n  Overall: {'PASS' if passed else 'FAIL'}")

    cleanup_test_data()

    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
