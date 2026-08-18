from datetime import datetime, timezone

from app.models import (
    Appointment,
    AppointmentStatus,
    ConversationChannel,
    ConversationSession,
    ConversationStatus,
    Department,
    Doctor,
    Patient,
    User,
    UserRole,
)
from app.services.audit import log_action
from app.services.auth import hash_password


def _seed_admin(db, role=UserRole.admin) -> User:
    user = User(email="staff@clinic.local", hashed_password=hash_password("s3cret!"), role=role)
    db.add(user)
    db.flush()
    return user


def _login(client, email="staff@clinic.local", password="s3cret!") -> str:
    resp = client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_front_desk_role_can_access_admin_routes(client, db):
    _seed_admin(db, role=UserRole.front_desk)
    db.commit()
    token = _login(client)

    resp = client.get("/api/admin/appointments", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_appointments_list_and_status_filter(client, db):
    _seed_admin(db)
    dept = Department(name="General Medicine")
    db.add(dept)
    db.flush()
    doctor = Doctor(full_name="Dr. Test", specialty="GP", department_id=dept.id)
    db.add(doctor)
    db.flush()
    patient = Patient(full_name="Pat", phone="+1900")
    db.add(patient)
    db.flush()
    db.add(
        Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            slot_start=datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc),
            slot_end=datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc),
            status=AppointmentStatus.confirmed,
        )
    )
    db.add(
        Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            slot_start=datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc),
            slot_end=datetime(2026, 9, 2, 9, 30, tzinfo=timezone.utc),
            status=AppointmentStatus.cancelled,
        )
    )
    db.commit()
    token = _login(client)

    resp = client.get("/api/admin/appointments", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp = client.get(
        "/api/admin/appointments", params={"status": "confirmed"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "confirmed"


def test_doctor_calendar_groups_by_doctor(client, db):
    _seed_admin(db)
    dept = Department(name="General Medicine")
    db.add(dept)
    db.flush()
    doctor = Doctor(full_name="Dr. Test", specialty="GP", department_id=dept.id)
    db.add(doctor)
    db.commit()
    token = _login(client)

    resp = client.get("/api/admin/doctors/calendar", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["doctor_name"] == "Dr. Test"
    assert body[0]["appointments"] == []


def test_audit_log_returns_recent_entries(client, db):
    _seed_admin(db)
    log_action(db, actor="system", action="test.one", entity_type="X", entity_id="1")
    log_action(db, actor="system", action="test.two", entity_type="X", entity_id="2")
    db.commit()
    token = _login(client)

    resp = client.get("/api/admin/audit-log", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    actions = [row["action"] for row in resp.json()]
    assert "test.one" in actions and "test.two" in actions


def test_emergencies_lists_flagged_sessions_and_acknowledge_closes_them(client, db):
    _seed_admin(db)
    patient = Patient(full_name="Pat", phone="+1900")
    db.add(patient)
    db.flush()
    session = ConversationSession(
        channel=ConversationChannel.web_chat,
        external_id="+1900",
        patient_id=patient.id,
        state={"stage": "emergency"},
        history=[{"role": "assistant", "content": "please seek help", "ts": "now"}],
        is_emergency=True,
    )
    db.add(session)
    db.commit()
    token = _login(client)

    resp = client.get("/api/admin/emergencies", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "active"

    resp = client.post(f"/api/admin/emergencies/{session.id}/acknowledge", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    db.refresh(session)
    assert session.status == ConversationStatus.closed
