"""Appointment Scheduling agent.

Deterministic by design (see CLAUDE.md working rules): finding slots and
booking is a DB query + simple text parsing problem, not a reasoning
problem, so there's no LLM involved here — a local model would only add
unreliability with no benefit.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Appointment, Doctor, Patient
from app.services.doctors import best_available_doctor
from app.services.scheduling import available_slots, book_appointment


def assign_doctor(db: Session, department_id: int) -> Doctor | None:
    return best_available_doctor(db, department_id)


def propose_slots(db: Session, doctor_id: int, limit: int = 5) -> list[tuple[datetime, datetime]]:
    return available_slots(db, doctor_id, limit=limit)


def format_slot_options(slots: list[tuple[datetime, datetime]]) -> str:
    if not slots:
        return "No upcoming availability found for this doctor in the next two weeks."
    lines = [f"{i + 1}. {start.strftime('%a %d %b, %H:%M')} UTC" for i, (start, _end) in enumerate(slots)]
    return "\n".join(lines)


def parse_slot_choice(user_text: str, slots: list[tuple[datetime, datetime]]) -> tuple[datetime, datetime] | None:
    stripped = user_text.strip()
    if stripped.isdigit():
        idx = int(stripped) - 1
        if 0 <= idx < len(slots):
            return slots[idx]
    return None


def confirm_booking(
    db: Session,
    patient: Patient,
    doctor: Doctor,
    slot: tuple[datetime, datetime],
    reason: str | None = None,
) -> Appointment:
    slot_start, slot_end = slot
    return book_appointment(db, patient.id, doctor.id, slot_start, slot_end, reason=reason)
