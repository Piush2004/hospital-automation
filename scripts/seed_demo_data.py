"""Seed the local DB with demo departments, doctors, availability, and
patients so every later phase (orchestrator, chat, dashboard) has
something real to work against.

Idempotent: safe to re-run — skips anything that already exists by
natural key (department name / doctor name / patient phone).

Usage (from backend/):
    .venv/Scripts/python ../scripts/seed_demo_data.py
"""

import sys
from datetime import date, time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.db import SessionLocal  # noqa: E402
from app.models import Department, Doctor, DoctorAvailability, Patient  # noqa: E402

DEPARTMENTS = [
    ("General Medicine", "First point of contact for most non-specialist complaints."),
    ("Cardiology", "Heart and cardiovascular system."),
    ("Pediatrics", "Care for infants, children, and adolescents."),
    ("Orthopedics", "Bones, joints, ligaments, and muscles."),
    ("Dermatology", "Skin, hair, and nail conditions."),
    ("ENT", "Ear, nose, and throat."),
]

# (name, specialty, department, weekday availability list of (day_of_week, start, end))
# day_of_week: 0=Mon .. 6=Sun
DOCTORS = [
    (
        "Dr. Ananya Rao",
        "General Physician",
        "General Medicine",
        [(0, time(9, 0), time(13, 0)), (2, time(9, 0), time(13, 0)), (4, time(9, 0), time(13, 0))],
    ),
    (
        "Dr. Vikram Shah",
        "General Physician",
        "General Medicine",
        [(1, time(14, 0), time(18, 0)), (3, time(14, 0), time(18, 0)), (5, time(9, 0), time(12, 0))],
    ),
    (
        "Dr. Priya Nair",
        "Cardiologist",
        "Cardiology",
        [(0, time(10, 0), time(14, 0)), (3, time(10, 0), time(14, 0))],
    ),
    (
        "Dr. Rohan Mehta",
        "Pediatrician",
        "Pediatrics",
        [(1, time(9, 0), time(13, 0)), (2, time(9, 0), time(13, 0)), (4, time(9, 0), time(13, 0))],
    ),
    (
        "Dr. Kavita Iyer",
        "Orthopedic Surgeon",
        "Orthopedics",
        [(0, time(15, 0), time(18, 0)), (4, time(15, 0), time(18, 0))],
    ),
    (
        "Dr. Sameer Khan",
        "Dermatologist",
        "Dermatology",
        [(2, time(14, 0), time(17, 0)), (5, time(10, 0), time(13, 0))],
    ),
    (
        "Dr. Neha Desai",
        "ENT Specialist",
        "ENT",
        [(1, time(10, 0), time(13, 0)), (3, time(15, 0), time(18, 0))],
    ),
]

PATIENTS = [
    ("Arjun Verma", "+919810000001", "arjun.verma@example.com", date(1990, 4, 12), "male"),
    ("Sneha Kapoor", "+919810000002", "sneha.kapoor@example.com", date(1985, 11, 2), "female"),
    ("Imran Sheikh", "+919810000003", "imran.sheikh@example.com", date(2001, 7, 23), "male"),
    ("Divya Menon", "+919810000004", "divya.menon@example.com", date(1978, 1, 30), "female"),
    ("Karan Malhotra", "+919810000005", "karan.malhotra@example.com", date(1995, 9, 15), "male"),
]


def seed() -> None:
    db = SessionLocal()
    try:
        dept_by_name: dict[str, Department] = {}
        for name, description in DEPARTMENTS:
            dept = db.query(Department).filter_by(name=name).one_or_none()
            if dept is None:
                dept = Department(name=name, description=description)
                db.add(dept)
                db.flush()
                print(f"+ department: {name}")
            dept_by_name[name] = dept

        for full_name, specialty, dept_name, availability in DOCTORS:
            doctor = db.query(Doctor).filter_by(full_name=full_name).one_or_none()
            if doctor is None:
                doctor = Doctor(
                    full_name=full_name,
                    specialty=specialty,
                    department_id=dept_by_name[dept_name].id,
                )
                db.add(doctor)
                db.flush()
                print(f"+ doctor: {full_name} ({specialty})")
                for day_of_week, start, end in availability:
                    db.add(
                        DoctorAvailability(
                            doctor_id=doctor.id,
                            day_of_week=day_of_week,
                            start_time=start,
                            end_time=end,
                            slot_minutes=20,
                        )
                    )

        for full_name, phone, email, dob, gender in PATIENTS:
            patient = db.query(Patient).filter_by(phone=phone).one_or_none()
            if patient is None:
                db.add(
                    Patient(
                        full_name=full_name,
                        phone=phone,
                        email=email,
                        date_of_birth=dob,
                        gender=gender,
                    )
                )
                print(f"+ patient: {full_name} ({phone})")

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
