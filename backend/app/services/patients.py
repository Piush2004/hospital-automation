from sqlalchemy.orm import Session

from app.models import Patient
from app.services.audit import log_action


def get_patient_by_phone(db: Session, phone: str) -> Patient | None:
    return db.query(Patient).filter_by(phone=phone).one_or_none()


def get_or_create_patient(db: Session, phone: str, full_name: str | None = None) -> Patient:
    patient = get_patient_by_phone(db, phone)
    if patient is not None:
        return patient

    patient = Patient(phone=phone, full_name=full_name or "Unknown")
    db.add(patient)
    db.flush()
    log_action(db, actor="system", action="patient.created", entity_type="Patient", entity_id=patient.id)
    return patient
