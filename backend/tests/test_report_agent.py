from datetime import datetime, timezone

import app.agents.report_agent as report_agent_module
from app.agents.report_agent import find_undelivered_report, generate_report
from app.models import Appointment, AppointmentStatus, Department, Doctor, Patient


class _FakeSettings:
    def __init__(self, reports_dir):
        self.reports_dir = reports_dir


def _seed_completed_appointment(db, notes: str = "Prescribed rest and fluids.") -> Appointment:
    dept = Department(name="General Medicine")
    db.add(dept)
    db.flush()
    doctor = Doctor(full_name="Dr. Report", specialty="GP", department_id=dept.id)
    db.add(doctor)
    db.flush()
    patient = Patient(full_name="Report Pat", phone="+1600")
    db.add(patient)
    db.flush()
    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        slot_start=datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc),
        slot_end=datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc),
        status=AppointmentStatus.completed,
        reason="Cough",
        notes=notes,
    )
    db.add(appointment)
    db.flush()
    return appointment


def test_generate_report_creates_pdf_and_row(db, tmp_path, monkeypatch):
    monkeypatch.setattr(report_agent_module, "get_settings", lambda: _FakeSettings(tmp_path))
    appointment = _seed_completed_appointment(db)

    report = generate_report(db, appointment)

    assert report.appointment_id == appointment.id
    assert report.generated_at is not None
    pdf_path = tmp_path / f"appointment_{appointment.id}_report.pdf"
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


def test_generate_report_is_idempotent_on_rerun(db, tmp_path, monkeypatch):
    monkeypatch.setattr(report_agent_module, "get_settings", lambda: _FakeSettings(tmp_path))
    appointment = _seed_completed_appointment(db)

    report1 = generate_report(db, appointment)
    report2 = generate_report(db, appointment)

    assert report1.id == report2.id


def test_find_undelivered_report_excludes_consented(db, tmp_path, monkeypatch):
    from datetime import datetime as dt

    monkeypatch.setattr(report_agent_module, "get_settings", lambda: _FakeSettings(tmp_path))
    appointment = _seed_completed_appointment(db)
    report = generate_report(db, appointment)

    found = find_undelivered_report(db, appointment.patient_id)
    assert found is not None and found.id == report.id

    report.consent_at = dt.now(timezone.utc)
    db.flush()

    assert find_undelivered_report(db, appointment.patient_id) is None
