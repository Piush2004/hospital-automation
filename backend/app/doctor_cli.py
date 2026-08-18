"""Crude internal tool for a doctor to mark a visit complete and attach
notes. No auth (see CLAUDE.md deviations — the app has no JWT/login flow
built yet, and standing one up just for this felt like scope creep ahead
of Phase 9's admin dashboard). This is explicitly the "or a small CLI
script" option, not the "minimal authenticated endpoint" one.

Usage (from backend/, with the venv active):
    .venv/Scripts/python -m app.doctor_cli
"""

import httpx

from app.agents.report_agent import generate_report
from app.agents.report_delivery_agent import consent_question
from app.config import get_settings
from app.db import SessionLocal
from app.models import Appointment, AppointmentStatus
from app.services import notifications
from app.services.appointments import complete_visit


def _try_live_push(patient_id: int) -> None:
    """Best-effort: if the API server is running and the patient has an
    open websocket connection, nudge it to show the consent question
    immediately instead of waiting for their next message. Doctor_cli
    works fine without this succeeding — see module docstring and
    app/channels/internal.py.
    """
    settings = get_settings()
    try:
        resp = httpx.post(f"{settings.app_base_url}/internal/push-live/{patient_id}", timeout=3.0)
        resp.raise_for_status()
    except httpx.HTTPError:
        print("(API server not reachable for live push - patient will see this on their next message.)")


def main() -> None:
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
            _try_live_push(appointment.patient_id)
        else:
            print("Patient has no active chat session right now - they'll see this next time they message in.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
