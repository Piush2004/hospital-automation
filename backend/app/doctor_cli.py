"""Crude internal tool for a doctor to mark a visit complete and attach
notes. As of Phase 9, the *dashboard* (see app/channels/doctor_dashboard.py)
is the primary, properly auth-gated way to do this day to day — this
script is kept as a scriptable fallback (demo_walkthrough.py uses its
functions directly, and it's handy for quick local testing without the
frontend running). Since /internal/push-live is now locked down behind
staff auth (see app/channels/internal.py), this script logs in first —
worth noting it's the exact same login endpoint the dashboard uses, so
this doubles as a rough manual check that staff auth actually works.

Usage (from backend/, with the venv active):
    .venv/Scripts/python -m app.doctor_cli
"""

import getpass

import httpx

from app.agents.report_agent import generate_report
from app.agents.report_delivery_agent import consent_question
from app.config import get_settings
from app.db import SessionLocal
from app.models import Appointment, AppointmentStatus
from app.services import notifications
from app.services.appointments import complete_visit


def _login() -> str | None:
    """Prompts for staff credentials and returns a bearer token, or None
    if login fails/is skipped — callers should degrade gracefully rather
    than treat this as fatal (see _try_live_push).
    """
    settings = get_settings()
    email = input("Staff email (blank to skip live-push login): ").strip()
    if not email:
        return None
    password = getpass.getpass("Password: ")
    try:
        resp = httpx.post(
            f"{settings.app_base_url}/auth/login",
            data={"username": email, "password": password},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except httpx.HTTPError as exc:
        print(f"Login failed ({exc}) - continuing without live push.")
        return None


def _try_live_push(patient_id: int, token: str | None) -> None:
    """Best-effort: if the API server is running, we're logged in, and the
    patient has an open websocket connection, nudge it to show the
    consent question immediately instead of waiting for their next
    message. Doctor_cli works fine without this succeeding — see module
    docstring and app/channels/internal.py.
    """
    if token is None:
        print("(No staff login - patient will see the consent question on their next message instead.)")
        return
    settings = get_settings()
    try:
        resp = httpx.post(
            f"{settings.app_base_url}/internal/push-live/{patient_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=3.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        print("(API server not reachable for live push - patient will see this on their next message.)")


def main() -> None:
    token = _login()
    db = SessionLocal()
    try:
        appointments = (
            db.query(Appointment)
            .filter_by(status=AppointmentStatus.confirmed)
            .order_by(Appointment.slot_start)
            .all()
        )
        if not appointments:
            print("No confirmed appointments waiting to be completed.")
            return

        print("Confirmed appointments:")
        for appt in appointments:
            print(
                f"  [{appt.id}] {appt.patient.full_name} with {appt.doctor.full_name} "
                f"on {appt.slot_start.strftime('%a %d %b, %H:%M')} UTC"
            )

        raw_id = input("\nAppointment id to complete: ").strip()
        if not raw_id.isdigit():
            print("Not a valid appointment id.")
            return
        appointment_id = int(raw_id)
        if appointment_id not in {a.id for a in appointments}:
            print("That id isn't in the confirmed list above.")
            return

        print("Enter visit notes (finish with an empty line):")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
        notes = "\n".join(lines).strip() or "No notes recorded."

        appointment = complete_visit(db, appointment_id, notes)
        report = generate_report(db, appointment)
        db.commit()
        print(f"\nVisit completed. Report generated at {report.file_path}")

        question = consent_question(report)
        sessions = notifications.queue_message_for_patient(
            db, appointment.patient_id, question, state_update={"awaiting_report_consent": {"report_id": report.id}}
        )
        db.commit()
        if sessions:
            print(f"Consent question queued for {len(sessions)} active session(s) for this patient.")
            _try_live_push(appointment.patient_id, token)
        else:
            print("Patient has no active chat session right now - they'll see this next time they message in.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
