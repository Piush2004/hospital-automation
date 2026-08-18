from app.models import User, UserRole
from app.services.auth import hash_password


def _make_user(db, email: str, role: UserRole, password: str = "correct-password") -> User:
    user = User(email=email, hashed_password=hash_password(password), role=role)
    db.add(user)
    db.flush()
    return user


def test_login_succeeds_with_correct_credentials(client, db):
    _make_user(db, "doc@clinic.local", UserRole.doctor, password="s3cret!")
    db.commit()

    resp = client.post("/auth/login", data={"username": "doc@clinic.local", "password": "s3cret!"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "doctor"
    assert body["access_token"]


def test_login_fails_with_wrong_password(client, db):
    _make_user(db, "doc@clinic.local", UserRole.doctor, password="s3cret!")
    db.commit()

    resp = client.post("/auth/login", data={"username": "doc@clinic.local", "password": "wrong"})

    assert resp.status_code == 401


def test_login_fails_for_unknown_email(client, db):
    resp = client.post("/auth/login", data={"username": "nobody@clinic.local", "password": "whatever"})
    assert resp.status_code == 401


def test_login_fails_for_patient_role(client, db):
    # Patients are phone-identified, not password-authenticated - even if
    # a User row somehow existed with role=patient, login must reject it.
    _make_user(db, "patient@example.com", UserRole.patient, password="s3cret!")
    db.commit()

    resp = client.post("/auth/login", data={"username": "patient@example.com", "password": "s3cret!"})
    assert resp.status_code == 401


def test_login_fails_for_inactive_user(client, db):
    user = _make_user(db, "doc@clinic.local", UserRole.doctor, password="s3cret!")
    user.is_active = False
    db.commit()

    resp = client.post("/auth/login", data={"username": "doc@clinic.local", "password": "s3cret!"})
    assert resp.status_code == 401


def test_protected_endpoint_rejects_missing_token(client, db):
    resp = client.get("/api/doctor/appointments")
    assert resp.status_code == 401


def test_protected_endpoint_rejects_garbage_token(client, db):
    resp = client.get("/api/doctor/appointments", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_role_gating_blocks_wrong_staff_role(client, db):
    _make_user(db, "doc@clinic.local", UserRole.doctor, password="s3cret!")
    db.commit()

    token = client.post("/auth/login", data={"username": "doc@clinic.local", "password": "s3cret!"}).json()[
        "access_token"
    ]

    resp = client.get("/api/admin/appointments", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_role_gating_allows_correct_staff_role(client, db):
    _make_user(db, "admin@clinic.local", UserRole.admin, password="s3cret!")
    db.commit()

    token = client.post("/auth/login", data={"username": "admin@clinic.local", "password": "s3cret!"}).json()[
        "access_token"
    ]

    resp = client.get("/api/admin/appointments", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_internal_push_live_requires_staff_auth(client, db):
    resp = client.post("/internal/push-live/1")
    assert resp.status_code == 401


def test_internal_push_live_accepts_valid_staff_token(client, db):
    _make_user(db, "doc@clinic.local", UserRole.doctor, password="s3cret!")
    db.commit()
    token = client.post("/auth/login", data={"username": "doc@clinic.local", "password": "s3cret!"}).json()[
        "access_token"
    ]

    resp = client.post("/internal/push-live/1", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_me_returns_linked_doctor_profile(client, db):
    from app.models import Department, Doctor

    dept = Department(name="General Medicine")
    db.add(dept)
    db.flush()
    user = _make_user(db, "doc@clinic.local", UserRole.doctor, password="s3cret!")
    doctor = Doctor(full_name="Dr. Test", specialty="GP", department_id=dept.id, user_id=user.id)
    db.add(doctor)
    db.commit()

    token = client.post("/auth/login", data={"username": "doc@clinic.local", "password": "s3cret!"}).json()[
        "access_token"
    ]

    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "Dr. Test"
    assert body["doctor_id"] == doctor.id
