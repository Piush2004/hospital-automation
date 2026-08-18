from datetime import datetime, timezone

from app.agents.payments_agent import confirm_payment, create_payment_link
from app.models import Appointment, AppointmentStatus, Department, Doctor, Patient, PaymentStatus


def _seed_appointment(db, fee: float = 500.00) -> Appointment:
    dept = Department(name="General Medicine")
    db.add(dept)
    db.flush()

    doctor = Doctor(full_name="Dr. Fee", specialty="GP", department_id=dept.id, consultation_fee=fee)
    db.add(doctor)
    db.flush()

    patient = Patient(full_name="Payer", phone="+1500")
    db.add(patient)
    db.flush()

    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        slot_start=datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc),
        slot_end=datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc),
        status=AppointmentStatus.pending_payment,
    )
    db.add(appointment)
    db.flush()
    return appointment


def test_create_payment_link_uses_doctor_fee(db):
    appointment = _seed_appointment(db, fee=650.00)

    payment, link = create_payment_link(db, appointment)

    assert float(payment.amount) == 650.00
    assert payment.provider == "mock"
    assert payment.status == PaymentStatus.pending
    assert payment.provider_ref == link.reference
    assert link.checkout_url.endswith(f"/pay/{link.reference}")


def test_confirm_payment_paid_confirms_appointment(db):
    appointment = _seed_appointment(db)
    payment, link = create_payment_link(db, appointment)

    confirm_payment(db, link.reference, outcome="paid")

    db.refresh(payment)
    db.refresh(appointment)
    assert payment.status == PaymentStatus.paid
    assert appointment.status == AppointmentStatus.confirmed


def test_confirm_payment_failed_leaves_appointment_pending(db):
    appointment = _seed_appointment(db)
    _payment, link = create_payment_link(db, appointment)

    confirm_payment(db, link.reference, outcome="failed")

    db.refresh(appointment)
    assert appointment.status == AppointmentStatus.pending_payment


def test_retry_after_failure_reuses_same_payment_row(db):
    appointment = _seed_appointment(db)
    payment, link = create_payment_link(db, appointment)
    confirm_payment(db, link.reference, outcome="failed")

    payment2, link2 = create_payment_link(db, appointment)

    assert payment2.id == payment.id
    assert link2.reference != link.reference
    assert payment2.status == PaymentStatus.pending


def test_confirm_payment_unknown_reference_raises(db):
    import pytest

    with pytest.raises(ValueError):
        confirm_payment(db, "does-not-exist", outcome="paid")
