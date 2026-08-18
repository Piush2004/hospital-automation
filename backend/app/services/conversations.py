from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import ConversationChannel, ConversationSession, ConversationStatus


def get_active_session(db: Session, channel: ConversationChannel, external_id: str) -> ConversationSession | None:
    return (
        db.query(ConversationSession)
        .filter_by(channel=channel, external_id=external_id, status=ConversationStatus.active)
        .order_by(ConversationSession.created_at.desc())
        .first()
    )


def create_session(
    db: Session,
    channel: ConversationChannel,
    external_id: str,
    patient_id: int | None,
    state: dict,
) -> ConversationSession:
    session = ConversationSession(
        channel=channel,
        external_id=external_id,
        patient_id=patient_id,
        state=state,
        history=[],
    )
    db.add(session)
    db.flush()
    return session


def append_history(session: ConversationSession, role: str, content: str) -> None:
    # Reassign (rather than .append) so SQLAlchemy's change tracking on the
    # JSON column actually picks up the mutation.
    session.history = [
        *session.history,
        {"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()},
    ]


def save_state(session: ConversationSession, state: dict, is_emergency: bool = False) -> None:
    session.state = state
    if is_emergency:
        session.is_emergency = True
