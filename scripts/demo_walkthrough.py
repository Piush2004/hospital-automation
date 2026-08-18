"""Scripted end-to-end demo of the full loop: book -> pay (mock) -> doctor
completes the visit with notes -> patient is asked for consent -> report
generated and delivered. Runnable end to end from a clean seed DB, no
manual typing required.

Usage (from backend/, with the venv active):
    .venv/Scripts/python ../scripts/demo_walkthrough.py

Safe to re-run: closes out any existing active session for the demo
phone number first, so every run gets a fresh transcript. Doctor
"completion" happens by calling the same functions app/doctor_cli.py
uses directly, since this script isn't interactive.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agents.orchestrator import initial_state, run_turn  # noqa: E402
from app.agents.payments_agent import confirm_payment  # noqa: E402
from app.agents.report_agent import generate_report  # noqa: E402
from app.agents.report_delivery_agent import consent_question  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.llm.ollama_client import OllamaClient  # noqa: E402
from app.models import ConversationChannel, ConversationStatus  # noqa: E402
from app.services import notifications  # noqa: E402
from app.services.appointments import complete_visit  # noqa: E402
from app.services.conversations import append_history, create_session, get_active_session  # noqa: E402
from app.services.patients import get_or_create_patient  # noqa: E402

DEMO_PHONE = "+919999000001"


def say_bot(text: str) -> None:
    print(f"bot> {text}\n")


def say_user(text: str) -> None:
    print(f"you> {text}\n")


def main() -> None:
    db = SessionLocal()
    llm = OllamaClient()
    if not llm.is_available():
        print("[info] Ollama not reachable - triage will use the keyword fallback.\n")

    try:
        # Fresh transcript every run.
        existing = get_active_session(db, ConversationChannel.web_chat, DEMO_PHONE)
        if existing is not None:
            existing.status = ConversationStatus.closed
            db.commit()

        patient = get_or_create_patient(db, DEMO_PHONE, full_name="Demo Patient")
        state, greeting = initial_state(patient)
        session = create_session(db, ConversationChannel.web_chat, DEMO_PHONE, patient.id, state)
        append_history(session, "assistant", greeting)
        db.commit()
        say_bot(greeting)

        def turn(user_input: str) -> None:
            nonlocal state
            say_user(user_input)
            append_history(session, "user", user_input)
            state, reply = run_turn(db, state, user_input, llm=llm)
            session.state = state
            append_history(session, "assistant", reply)
            db.commit()
            say_bot(reply)

        turn("I've had a persistent cough and chest tightness for a few days")
        turn("1")  # pick the first offered slot

        assert state["stage"] == "await_payment", f"expected await_payment, got {state['stage']}"

        print(f"[demo] Simulating the patient completing checkout for {state['payment_reference']}...\n")
        confirm_payment(db, state["payment_reference"], outcome="paid")
        db.commit()

        turn("hi again")  # reconciles: sees the payment cleared and closes out
        assert state["stage"] == "done"
        appointment_id = state["appointment_id"]
        print(f"[demo] Appointment #{appointment_id} is confirmed and paid.\n")

        print("[demo] Doctor completes the visit and attaches notes (via doctor_cli.py's functions)...\n")
        appointment = complete_visit(
            db,
            appointment_id,
            notes="Likely stress-related chest tightness. Recommended ECG follow-up and reduced caffeine intake.",
        )
        report = generate_report(db, appointment)
        db.commit()
        print(f"[demo] Report generated: {report.file_path}\n")

        question = consent_question(report)
        sessions = notifications.queue_message_for_patient(
            db, appointment.patient_id, question, state_update={"awaiting_report_consent": {"report_id": report.id}}
        )
        db.commit()
        state = sessions[0].state  # pick up the awaiting_report_consent flag doctor_cli would have set

        say_bot(question)
        turn("yes please")

        db.refresh(report)
        assert report.consent_at is not None and report.delivered_at is not None
        print(f"[demo] Done. Report #{report.id} was consented to and delivered in-chat.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
