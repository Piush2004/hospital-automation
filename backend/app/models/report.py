from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import DeliveryChannel
from app.models.mixins import TimestampMixin


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), unique=True, nullable=False)

    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Consent must be captured before delivery — see Report Delivery agent (Phase 6).
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_channel: Mapped[DeliveryChannel | None] = mapped_column(Enum(DeliveryChannel), nullable=True)

    appointment: Mapped["Appointment"] = relationship(back_populates="report")

    def __repr__(self) -> str:
        return f"<Report id={self.id} appointment_id={self.appointment_id} delivered_at={self.delivered_at}>"
