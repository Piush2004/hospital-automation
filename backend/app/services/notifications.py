"""Push a message into a patient's active conversation(s), on whichever
channel(s) they're on.

Split into a sync DB-persistence half (safe to call from anywhere,
including standalone scripts like doctor_cli.py) and an async live-push
half (only meaningful inside the FastAPI process — see
app/services/live_connections.py).
"""

import logging

from sqlalchemy.orm import Session

from app.models import ConversationSession, ConversationStatus, Patient
from app.services import live_connections
from app.services.conversations import append_history

logger = logging.getLogger(__name__)


def queue_message_for_patient(
    db: Session,
    patient_id: int,
    content: str,
    state_update: dict | None = None,
) -> list[ConversationSession]:
    """Appends `content` as an assistant message to every active session
    this patient has (there's normally at most one, but a patient could
    in principle be active on two channels at once). Returns the updated
    sessions so a caller with async/live-push access can also try that.
    """
    sessions = (
        db.query(ConversationSession)
        .filter_by(patient_id=patient_id, status=ConversationStatus.active)
        .all()
    )
    for session in sessions:
        append_history(session, "assistant", content)
        if state_update:
            session.state = {**session.state, **state_update}
    db.commit()
    return sessions


async def push_live(sessions: list[ConversationSession]) -> None:
    """Best-effort real-time delivery for any of `sessions` that currently
    have an open connection. Silently does nothing for sessions that
    aren't live — the message is already persisted by
    queue_message_for_patient, so it'll surface next time that channel's
    adapter loads the session (see the *_node reconciliation pattern in
    orchestrator.py).
    """
    for session in sessions:
        connection = live_connections.get(session.channel, session.external_id)
        if connection is None:
            continue
        try:
            last_message = session.history[-1]["content"] if session.history else ""
            await connection.send_json(
                {"role": "assistant", "content": last_message, "stage": session.state.get("stage")}
            )
        except Exception:
            logger.warning("Live push failed for session %s", session.id, exc_info=True)
