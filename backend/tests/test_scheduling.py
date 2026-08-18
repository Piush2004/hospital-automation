from datetime import time

from app.models import Department, Doctor, DoctorAvailability, Patient
from app.services.scheduling import available_slots, book_appointment


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
