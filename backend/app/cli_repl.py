"""Plain-text REPL for exercising the orchestrator end-to-end without any
HTTP layer — the Phase 2/3 smoke test described in CLAUDE.md.

Usage (from backend/, with the venv active):
    .venv/Scripts/python -m app.cli_repl [phone]

If no phone is given, defaults to one of the seeded demo patients so you
can try the flow immediately without creating a new record.
"""

import sys

from app.agents.orchestrator import initial_state, run_turn
from app.db import SessionLocal
from app.llm.ollama_client import OllamaClient
from app.models import ConversationChannel
from app.services.conversations import append_history, create_session, get_active_session, save_state
from app.services.patients import get_or_create_patient

DEFAULT_PHONE = "+919810000001"  # Arjun Verma, seeded in scripts/seed_demo_data.py


def main() -> None:
    phone = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PHONE
    db = SessionLocal()
    llm = OllamaClient()

    if not llm.is_available():
        print(
            f"[warning] Ollama not reachable at its configured base URL — "
            f"triage will fall back to keyword matching.\n"
        )

    try:
        patient = get_or_create_patient(db, phone)
        session = get_active_session(db, ConversationChannel.web_chat, phone)

        if session is None:
            state, greeting = initial_state(patient)
            session = create_session(db, ConversationChannel.web_chat, phone, patient.id, state)
            append_history(session, "assistant", greeting)
            db.commit()
            print(f"bot> {greeting}")
        else:
            state = session.state
            print(f"(resuming session #{session.id}, stage={state.get('stage')})")
            if session.history:
                print(f"bot> {session.history[-1]['content']}")

        while True:
            try:
                user_input = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if user_input.lower() in {"quit", "exit"}:
                break
            if not user_input:
                continue

            append_history(session, "user", user_input)

            new_state, reply = run_turn(db, state, user_input, llm=llm)
            state = new_state
            save_state(session, state, is_emergency=state.get("is_emergency", False))
            append_history(session, "assistant", reply)
            db.commit()

            print(f"bot> {reply}")

            if state.get("stage") == "emergency":
                break
    finally:
        db.close()


if __name__ == "__main__":
    main()
