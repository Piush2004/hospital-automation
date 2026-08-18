from datetime import time

import pytest

from app.models import AppointmentStatus, Department, Doctor, DoctorAvailability, Patient
from app.services.scheduling import SlotAlreadyBookedError, available_slots, book_appointment


def _make_doctor(db, day_of_week: int, start: time, end: time, slot_minutes: int = 30) -> Doctor:
    dept = Department(name="General Medicine")
    db.add(dept)
    db.flush()

    doctor = Doctor(full_name="Dr. Test", specialty="GP", department_id=dept.id)
    db.add(doctor)
    db.flush()

    db.add(
        DoctorAvailability(
            doctor_id=doctor.id,
            day_of_week=day_of_week,
            start_time=start,
            end_time=end,
            slot_minutes=slot_minutes,
        )
    )
    db.flush()
    return doctor


def test_available_slots_respects_weekly_window(db, monkeypatch):
    from datetime import datetime, timezone

    # Fix "now" to a known Monday so the test isn't day-of-week dependent.
    fixed_now = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)  # a Monday

    doctor = _make_doctor(db, day_of_week=0, start=time(9, 0), end=time(10, 0), slot_minutes=30)

    slots = available_slots(db, doctor.id, days_ahead=7, limit=10, now=fixed_now)

    assert len(slots) == 2
    assert slots[0][0].hour == 9
    assert slots[1][0].hour == 9 and slots[1][0].minute == 30


def test_available_slots_excludes_booked(db):
    from datetime import datetime, timezone

    fixed_now = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)

    doctor = _make_doctor(db, day_of_week=0, start=time(9, 0), end=time(10, 0), slot_minutes=30)
    patient = Patient(full_name="P", phone="+1000")
    db.add(patient)
    db.flush()

    book_appointment(db, patient.id, doctor.id, fixed_now.replace(hour=9, minute=0), fixed_now.replace(hour=9, minute=30))
    db.flush()

    slots = available_slots(db, doctor.id, days_ahead=7, limit=10, now=fixed_now)

    assert len(slots) == 1
    assert slots[0][0].hour == 9 and slots[0][0].minute == 30


def test_double_booking_same_doctor_slot_raises(db):
    """The actual DB-level guard against the race condition found via
    stress-testing concurrent bookings - see Appointment.__table_args__.
    """
    from datetime import datetime, timezone

    doctor = _make_doctor(db, day_of_week=0, start=time(9, 0), end=time(10, 0))
    patient1 = Patient(full_name="P1", phone="+1000")
    patient2 = Patient(full_name="P2", phone="+1001")
    db.add_all([patient1, patient2])
    db.flush()

    start = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc)

    book_appointment(db, patient1.id, doctor.id, start, end)

    with pytest.raises(SlotAlreadyBookedError):
        book_appointment(db, patient2.id, doctor.id, start, end)


def test_double_booking_allowed_after_first_is_cancelled(db):
    """The partial index only covers active statuses - a cancelled slot
    should be rebookable.
    """
    from datetime import datetime, timezone

    doctor = _make_doctor(db, day_of_week=0, start=time(9, 0), end=time(10, 0))
    patient1 = Patient(full_name="P1", phone="+1002")
    patient2 = Patient(full_name="P2", phone="+1003")
    db.add_all([patient1, patient2])
    db.flush()

    start = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc)

    first = book_appointment(db, patient1.id, doctor.id, start, end)
    first.status = AppointmentStatus.cancelled
    db.flush()

    second = book_appointment(db, patient2.id, doctor.id, start, end)
    assert second.id != first.id


def test_book_appointment_writes_audit_log(db):
    from app.models import AuditLog
    from datetime import datetime, timezone

    doctor = _make_doctor(db, day_of_week=0, start=time(9, 0), end=time(10, 0))
    patient = Patient(full_name="P", phone="+1000")
    db.add(patient)
    db.flush()

    start = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
    appt = book_appointment(db, patient.id, doctor.id, start, start)

    logs = db.query(AuditLog).filter_by(entity_type="Appointment", entity_id=str(appt.id)).all()
    assert len(logs) == 1
    assert logs[0].action == "appointment.booked"
