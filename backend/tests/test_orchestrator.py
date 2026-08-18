from datetime import time

from app.agents.orchestrator import initial_state, run_turn
from app.agents.payments_agent import confirm_payment
from app.models import Appointment, AppointmentStatus, Department, Doctor, DoctorAvailability, Patient, Payment


class _StubLLM:
    def chat_json(self, messages, temperature=0.1, retries=2):
        return {"department": "Dermatology", "reasoning": "skin symptoms"}


def _seed(db) -> Doctor:
    dept = Department(name="Dermatology")
    db.add(dept)
    db.flush()

    doctor = Doctor(full_name="Dr. Test", specialty="Dermatologist", department_id=dept.id)
    db.add(doctor)
    db.flush()

    # Wide-open availability every day so the test doesn't depend on real
    # wall-clock time landing inside a narrow window.
    for day_of_week in range(7):
        db.add(
            DoctorAvailability(
                doctor_id=doctor.id,
                day_of_week=day_of_week,
                start_time=time(0, 0),
                end_time=time(23, 30),
                slot_minutes=30,
            )
        )
    db.flush()
    return doctor


def test_full_conversation_books_appointment(db):
    doctor = _seed(db)
    patient = Patient(full_name="Unknown", phone="+1000")
    db.add(patient)
    db.flush()

    llm = _StubLLM()

    state, greeting = initial_state(patient)
    assert state["stage"] == "collect_name"
    assert "name" in greeting.lower()

    state, reply = run_turn(db, state, "John Doe", llm=llm)
    assert state["stage"] == "collect_symptom"
    assert "John Doe" in reply

    state, reply = run_turn(db, state, "I have a bad skin rash", llm=llm)
    assert state["stage"] == "choose_slot"
    assert state["department_name"] == "Dermatology"
    assert state["doctor_id"] == doctor.id
    assert len(state["candidate_slots"]) > 0
    assert "Dr. Test" in reply

    state, reply = run_turn(db, state, "1", llm=llm)
    assert state["stage"] == "await_payment"
    assert state["appointment_id"] is not None
    assert "pay" in reply.lower()
    assert state["payment_reference"]

    appt = db.get(Appointment, state["appointment_id"])
    assert appt.patient_id == patient.id
    assert appt.doctor_id == doctor.id
    assert appt.status == AppointmentStatus.pending_payment

    # Simulate the patient completing checkout on the (mock) payment page,
    # out of band from the chat turn loop.
    confirm_payment(db, state["payment_reference"], outcome="paid")
    db.refresh(appt)
    assert appt.status == AppointmentStatus.confirmed

    # Next chat turn should reconcile from the DB and close out the flow.
    state, reply = run_turn(db, state, "hello?", llm=llm)
    assert state["stage"] == "done"
    assert "confirmed" in reply.lower()


def test_payment_failure_offers_retry_link(db):
    doctor = _seed(db)
    patient = Patient(full_name="Retry Pat", phone="+1003")
    db.add(patient)
    db.flush()

    llm = _StubLLM()
    state, _greeting = initial_state(patient)
    state, _reply = run_turn(db, state, "skin rash", llm=llm)
    state, _reply = run_turn(db, state, "1", llm=llm)
    assert state["stage"] == "await_payment"
    first_reference = state["payment_reference"]

    confirm_payment(db, first_reference, outcome="failed")

    payment = db.query(Payment).filter_by(appointment_id=state["appointment_id"]).one()
    assert payment.status.value == "failed"

    state, reply = run_turn(db, state, "hello?", llm=llm)
    assert state["stage"] == "await_payment"
    assert state["payment_reference"] != first_reference
    assert "fresh link" in reply.lower()


def test_emergency_short_circuits_flow(db):
    patient = Patient(full_name="Jane Doe", phone="+1001")
    db.add(patient)
    db.flush()

    llm = _StubLLM()
    state, _greeting = initial_state(patient)
    assert state["stage"] == "collect_symptom"

    state, reply = run_turn(db, state, "I have severe chest pain and can't breathe", llm=llm)

    assert state["is_emergency"] is True
    assert state["stage"] == "emergency"
    assert "emergency" in reply.lower()


def test_slot_taken_by_race_reoffers_fresh_slots(db):
    """Simulates the exact race stress-testing found: between offering a
    slot and the patient's reply arriving, someone else books that same
    slot first. The orchestrator should recover, not crash the turn.
    """
    from datetime import datetime

    from app.services.scheduling import book_appointment

    doctor = _seed(db)
    patient = Patient(full_name="Racer", phone="+1004")
    other_patient = Patient(full_name="Winner", phone="+1005")
    db.add_all([patient, other_patient])
    db.flush()

    llm = _StubLLM()
    state, _greeting = initial_state(patient)
    state, _reply = run_turn(db, state, "skin rash", llm=llm)
    assert state["stage"] == "choose_slot"

    # Someone else grabs the first offered slot first.
    first_slot_start, first_slot_end = state["candidate_slots"][0]
    book_appointment(
        db, other_patient.id, doctor.id, datetime.fromisoformat(first_slot_start), datetime.fromisoformat(first_slot_end)
    )
    db.commit()

    state, reply = run_turn(db, state, "1", llm=llm)

    assert state["stage"] == "choose_slot"  # re-offered, not crashed
    assert "just taken" in reply.lower()
    assert "reply with a number" in reply.lower()
    # The re-offered list should no longer include the now-taken slot first.
    assert state["candidate_slots"][0][0] != first_slot_start


def test_invalid_slot_choice_reprompts(db):
    doctor = _seed(db)
    patient = Patient(full_name="Bob", phone="+1002")
    db.add(patient)
    db.flush()

    llm = _StubLLM()
    state, _greeting = initial_state(patient)
    state, _reply = run_turn(db, state, "skin rash", llm=llm)
    assert state["stage"] == "choose_slot"

    state, reply = run_turn(db, state, "not a number", llm=llm)

    assert state["stage"] == "choose_slot"
    assert "please reply with a number" in reply.lower()
