from sqlalchemy import JSON, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import ConversationChannel, ConversationStatus
from app.models.mixins import TimestampMixin


class ConversationSession(Base, TimestampMixin):
    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[ConversationChannel] = mapped_column(Enum(ConversationChannel), nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus), default=ConversationStatus.active, nullable=False
    )
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True)

    # Channel-specific identity before a Patient record is linked, e.g. a
    # WhatsApp phone number or a random web-chat session token.
    external_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    # LangGraph state snapshot (current node, slots collected so far, etc).
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Full message history: list[{"role": ..., "content": ..., "ts": ...}]
    history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    is_emergency: Mapped[bool] = mapped_column(default=False, nullable=False)

    patient: Mapped["Patient | None"] = relationship(back_populates="conversation_sessions")

    def __repr__(self) -> str:
        return f"<ConversationSession id={self.id} channel={self.channel} external_id={self.external_id!r}>"
