from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import PaymentStatus
from app.models.mixins import TimestampMixin


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), unique=True, nullable=False)

    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.pending, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    appointment: Mapped["Appointment"] = relationship(back_populates="payment")

    def __repr__(self) -> str:
        return f"<Payment id={self.id} appointment_id={self.appointment_id} status={self.status} amount={self.amount}>"
