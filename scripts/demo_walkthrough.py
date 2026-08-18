"""Scripted end-to-end demo: books a real appointment against the seeded
DB, pays for it (mock), and prints a readable transcript. This is the
smoke test to run after `seed_demo_data.py` to prove the whole loop
still works — no manual typing required.

Usage (from backend/, with the venv active):
    .venv/Scripts/python ../scripts/demo_walkthrough.py

Safe to re-run: closes out any existing active session for the demo
phone number first, so every run gets a fresh transcript.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agents.orchestrator import initial_state, run_turn  # noqa: E402
from app.agents.payments_agent import confirm_payment  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.llm.ollama_client import OllamaClient  # noqa: E402
from app.models import ConversationChannel, ConversationStatus  # noqa: E402
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
        print("[info] Ollama not reachable — triage will use the keyword fallback.\n")

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

        turns = ["I've had a persistent cough and chest tightness for a few days"]

        for user_input in turns:
            say_user(user_input)
            append_history(session, "user", user_input)
            state, reply = run_turn(db, state, user_input, llm=llm)
            session.state = state
            append_history(session, "assistant", reply)
            db.commit()
            say_bot(reply)

        # Pick the first offered slot.
        say_user("1")
        append_history(session, "user", "1")
        state, reply = run_turn(db, state, "1", llm=llm)
        session.state = state
        append_history(session, "assistant", reply)
        db.commit()
        say_bot(reply)

        assert state["stage"] == "await_payment", f"expected await_payment, got {state['stage']}"

        print(f"[demo] Simulating the patient completing checkout for {state['payment_reference']}...\n")
        confirm_payment(db, state["payment_reference"], outcome="paid")
        db.commit()

        # Next turn reconciles: sees the payment cleared and closes out.
        say_user("(returns to chat)")
        state, reply = run_turn(db, state, "hi again", llm=llm)
        session.state = state
        append_history(session, "assistant", reply)
        db.commit()
        say_bot(reply)

        print(f"[demo] Done. Appointment #{state['appointment_id']} is now confirmed and paid.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
