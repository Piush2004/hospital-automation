from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin


class Patient(Base, TimestampMixin):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True, nullable=True)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # phone is the identity anchor for patients who reach us via chat/WhatsApp
    # without ever creating a User account.
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)

    user: Mapped["User | None"] = relationship(back_populates="patient")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="patient")
    conversation_sessions: Mapped[list["ConversationSession"]] = relationship(back_populates="patient")

    def __repr__(self) -> str:
        return f"<Patient id={self.id} name={self.full_name!r} phone={self.phone!r}>"
