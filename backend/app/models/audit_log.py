from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "system", "user:42", "agent:scheduling"
    action: Mapped[str] = mapped_column(String(120), nullable=False)  # e.g. "appointment.booked"
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)  # e.g. "Appointment"
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} actor={self.actor!r} action={self.action!r}>"
