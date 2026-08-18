from datetime import datetime, timezone

from app.models import (
    Appointment,
    AppointmentStatus,
    ConversationChannel,
    ConversationSession,
    Department,
    Doctor,
    Patient,
    Report,
    User,
    UserRole,
)
from app.services.auth import hash_password


def _seed_doctor_with_login(db, email="doc@clinic.local", password="s3cret!") -> tuple[User, Doctor]:
    dept = db.query(Department).filter_by(name="General Medicine").one_or_none()
    if dept is None:
        dept = Department(name="General Medicine")
        db.add(dept)
        db.flush()
    user = User(email=email, hashed_password=hash_password(password), role=UserRole.doctor)
    db.add(user)
    db.flush()
    doctor = Doctor(full_name="Dr. Test", specialty="GP", department_id=dept.id, user_id=user.id)
    db.add(doctor)
    db.flush()
    return user, doctor


def _seed_confirmed_appointment(db, doctor: Doctor, phone: str = "+1900") -> Appointment:
    patient = Patient(full_name="Pat", phone=phone)
    db.add(patient)
    db.flush()
    appt = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        slot_start=datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc),
        slot_end=datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc),
        status=AppointmentStatus.confirmed,
        reason="Checkup",
    )
    db.add(appt)
    db.flush()
    return appt


def _login(client, email, password="s3cret!") -> str:
    resp = client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_list_appointments_scoped_to_own_doctor_only(client, db):
    _user, doctor = _seed_doctor_with_login(db)
    _other_user, other_doctor = _seed_doctor_with_login(db, email="other@clinic.local")
    _seed_confirmed_appointment(db, doctor, phone="+1901")
    _seed_confirmed_appointment(db, other_doctor, phone="+1902")
    db.commit()

    token = _login(client, "doc@clinic.local")
    resp = client.get("/api/doctor/appointments", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["patient_phone"] == "+1901"


def test_complete_visit_matches_doctor_cli_outcome(client, db, tmp_path, monkeypatch):
    """The dashboard's complete-visit call should produce the exact same
    DB state doctor_cli.py's direct service calls do: appointment
    completed with notes, a Report row generated, and a consent question
    + awaiting_report_consent flag queued into the patient's active
    session.
    """
    import app.agents.report_agent as report_agent_module

    class _FakeSettings:
        reports_dir = tmp_path

    monkeypatch.setattr(report_agent_module, "get_settings", lambda: _FakeSettings())

    _user, doctor = _seed_doctor_with_login(db)
    appt = _seed_confirmed_appointment(db, doctor)
    session = ConversationSession(
        channel=ConversationChannel.web_chat,
        external_id="+1900",
        patient_id=appt.patient_id,
        state={"stage": "done"},
        history=[],
    )
    db.add(session)
    db.commit()

    token = _login(client, "doc@clinic.local")
    resp = client.post(
        f"/api/doctor/appointments/{appt.id}/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"notes": "All good, prescribed rest."},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["sessions_notified"] == 1

    db.refresh(appt)
    assert appt.status == AppointmentStatus.completed
    assert appt.notes == "All good, prescribed rest."

    report = db.query(Report).filter_by(appointment_id=appt.id).one()
    assert report.id == body["report_id"]
    assert report.generated_at is not None

    db.refresh(session)
    assert session.state.get("awaiting_report_consent") == {"report_id": report.id}
    assert "ready" in session.history[-1]["content"].lower()


def test_complete_visit_rejects_another_doctors_appointment(client, db):
    _user, doctor = _seed_doctor_with_login(db)
    _other_user, other_doctor = _seed_doctor_with_login(db, email="other@clinic.local")
    other_appt = _seed_confirmed_appointment(db, other_doctor)
    db.commit()

    token = _login(client, "doc@clinic.local")
    resp = client.post(
        f"/api/doctor/appointments/{other_appt.id}/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"notes": "shouldn't work"},
    )

    assert resp.status_code == 404
    db.refresh(other_appt)
    assert other_appt.status == AppointmentStatus.confirmed  # untouched


def test_complete_visit_rejects_nonexistent_appointment(client, db):
    _user, _doctor = _seed_doctor_with_login(db)
    db.commit()

    token = _login(client, "doc@clinic.local")
    resp = client.post(
        "/api/doctor/appointments/9999/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"notes": "n/a"},
    )
    assert resp.status_code == 404


def test_doctor_without_linked_profile_gets_clear_error(client, db):
    user = User(email="unlinked@clinic.local", hashed_password=hash_password("s3cret!"), role=UserRole.doctor)
    db.add(user)
    db.commit()

    token = _login(client, "unlinked@clinic.local")
    resp = client.get("/api/doctor/appointments", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400
