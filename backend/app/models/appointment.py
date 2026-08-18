from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import AppointmentStatus
from app.models.mixins import TimestampMixin

# Active statuses, inlined as literal strings for the partial-index WHERE
# clause below (can't reference services/doctors.ACTIVE_STATUSES here -
# that module imports from models, and DDL needs literal SQL anyway).
# Keep in sync with app.services.doctors.ACTIVE_STATUSES.
_ACTIVE_STATUS_VALUES = ("requested", "pending_payment", "confirmed")


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"
    __table_args__ = (
        # DB-level enforcement against double-booking: two active
        # appointments can never share the same (doctor, slot_start).
        # Found by stress-testing concurrent bookings — the application
        # was only checking "is this slot free?" then inserting, with no
        # atomicity between the two, so two concurrent requests could both
        # pass the check. book_appointment() catches the resulting
        # IntegrityError and turns it into SlotAlreadyBookedError; see
        # app/services/scheduling.py.
        Index(
            "ix_appointments_doctor_slot_active",
            "doctor_id",
            "slot_start",
            unique=True,
            sqlite_where=text(
                "status IN (" + ", ".join(f"'{v}'" for v in _ACTIVE_STATUS_VALUES) + ")"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), nullable=False)

    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), default=AppointmentStatus.requested, nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    patient: Mapped["Patient"] = relationship(back_populates="appointments")
    doctor: Mapped["Doctor"] = relationship(back_populates="appointments")
    payment: Mapped["Payment | None"] = relationship(back_populates="appointment", uselist=False)
    report: Mapped["Report | None"] = relationship(back_populates="appointment", uselist=False)

    def __repr__(self) -> str:
        return f"<Appointment id={self.id} patient_id={self.patient_id} doctor_id={self.doctor_id} status={self.status}>"
