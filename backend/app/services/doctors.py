from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, Doctor

ACTIVE_STATUSES = (AppointmentStatus.requested, AppointmentStatus.pending_payment, AppointmentStatus.confirmed)


def list_doctors_by_department(db: Session, department_id: int) -> list[Doctor]:
    return (
        db.query(Doctor)
        .filter(Doctor.department_id == department_id, Doctor.is_active.is_(True))
        .order_by(Doctor.full_name)
        .all()
    )


def doctor_current_load(db: Session, doctor_id: int) -> int:
    """Count of this doctor's active (not cancelled/completed) upcoming appointments."""
    now = datetime.now(timezone.utc)
    return (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.doctor_id == doctor_id,
            Appointment.status.in_(ACTIVE_STATUSES),
            Appointment.slot_start >= now,
        )
        .scalar()
        or 0
    )


def best_available_doctor(db: Session, department_id: int) -> Doctor | None:
    """Pick the doctor in this department with the lowest current upcoming load.

    Simple load-balancing heuristic for triage/assignment — no seniority or
    rating weighting yet.
    """
    doctors = list_doctors_by_department(db, department_id)
    if not doctors:
        return None
    return min(doctors, key=lambda d: doctor_current_load(db, d.id))
