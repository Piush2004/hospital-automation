from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, Doctor, DoctorAvailability
from app.services.audit import log_action
from app.services.doctors import ACTIVE_STATUSES

# MVP note: everything is treated as UTC. A real deployment would carry a
# hospital/doctor timezone; out of scope for the local prototype.


def _existing_slots(db: Session, doctor_id: int, window_start: datetime, window_end: datetime) -> set[datetime]:
    rows = (
        db.query(Appointment.slot_start)
        .filter(
            Appointment.doctor_id == doctor_id,
            Appointment.status.in_(ACTIVE_STATUSES),
            Appointment.slot_start >= window_start,
            Appointment.slot_start < window_end,
        )
        .all()
    )
    # SQLite's DateTime(timezone=True) doesn't actually round-trip tzinfo —
    # values come back naive. Re-attach UTC (our one and only timezone, per
    # the module note above) so comparisons against tz-aware generated
    # slots below work instead of silently never matching.
    return {(r[0] if r[0].tzinfo else r[0].replace(tzinfo=timezone.utc)) for r in rows}


def available_slots(
    db: Session,
    doctor_id: int,
    days_ahead: int = 14,
    limit: int = 5,
    now: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """Weekly availability windows minus already-booked slots, next `limit` results."""
    now = now or datetime.now(timezone.utc)
    window_end = now + timedelta(days=days_ahead)

    availability = db.query(DoctorAvailability).filter_by(doctor_id=doctor_id).all()
    if not availability:
        return []

    booked = _existing_slots(db, doctor_id, now, window_end)

    by_weekday: dict[int, list[DoctorAvailability]] = {}
    for row in availability:
        by_weekday.setdefault(row.day_of_week, []).append(row)

    results: list[tuple[datetime, datetime]] = []
    day_cursor = now.date()
    for _ in range(days_ahead):
        windows = by_weekday.get(day_cursor.weekday(), [])
        for window in windows:
            slot_start = datetime.combine(day_cursor, window.start_time, tzinfo=timezone.utc)
            day_end = datetime.combine(day_cursor, window.end_time, tzinfo=timezone.utc)
            step = timedelta(minutes=window.slot_minutes)
            while slot_start + step <= day_end:
                if slot_start >= now and slot_start not in booked:
                    results.append((slot_start, slot_start + step))
                    if len(results) >= limit:
                        return results
                slot_start += step
        day_cursor += timedelta(days=1)

    return results


def book_appointment(
    db: Session,
    patient_id: int,
    doctor_id: int,
    slot_start: datetime,
    slot_end: datetime,
    reason: str | None = None,
    status: AppointmentStatus = AppointmentStatus.pending_payment,
) -> Appointment:
    """Creates the appointment. Status defaults to `pending_payment` — the
    booking isn't `confirmed` until payments_agent.confirm_payment() flips
    it (see app/agents/payments_agent.py). Slot-exclusion treats
    pending_payment as active (see doctors.ACTIVE_STATUSES) so a second
    patient can't grab the same slot while payment is outstanding.
    """
    appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        slot_start=slot_start,
        slot_end=slot_end,
        status=status,
        reason=reason,
    )
    db.add(appointment)
    db.flush()
    log_action(
        db,
        actor="agent:scheduling",
        action="appointment.booked",
        entity_type="Appointment",
        entity_id=appointment.id,
        details={"patient_id": patient_id, "doctor_id": doctor_id, "slot_start": slot_start.isoformat()},
    )
    return appointment
