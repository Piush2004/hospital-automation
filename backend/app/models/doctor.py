from datetime import time

from sqlalchemy import ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin


class Doctor(Base, TimestampMixin):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True, nullable=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)

    # Expected to include any honorific ("Dr. Jane Doe") — there's no
    # separate title field, and chat replies interpolate this as-is.
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialty: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    # simple load-balancing signal for triage: max concurrent active appointments
    max_daily_appointments: Mapped[int] = mapped_column(Integer, default=16, nullable=False)

    user: Mapped["User | None"] = relationship(back_populates="doctor")
    department: Mapped["Department"] = relationship(back_populates="doctors")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="doctor")
    availability_slots: Mapped[list["DoctorAvailability"]] = relationship(
        back_populates="doctor", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Doctor id={self.id} name={self.full_name!r} specialty={self.specialty!r}>"


class DoctorAvailability(Base):
    """Recurring weekly availability window, e.g. Mon 09:00-13:00.

    MVP-level: no holiday/exception calendar yet. Free-slot search =
    these windows minus existing (non-cancelled) Appointments.
    """

    __tablename__ = "doctor_availability"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), nullable=False)
    # 0 = Monday .. 6 = Sunday (Python's date.weekday())
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_minutes: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    doctor: Mapped["Doctor"] = relationship(back_populates="availability_slots")

    def __repr__(self) -> str:
        return f"<DoctorAvailability doctor_id={self.doctor_id} dow={self.day_of_week} {self.start_time}-{self.end_time}>"
