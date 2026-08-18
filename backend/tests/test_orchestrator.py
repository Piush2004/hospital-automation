from datetime import time

from app.agents.orchestrator import initial_state, run_turn
from app.models import Appointment, Department, Doctor, DoctorAvailability, Patient


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
    assert state["stage"] == "done"
    assert state["appointment_id"] is not None
    assert "booked" in reply.lower()

    appt = db.get(Appointment, state["appointment_id"])
    assert appt.patient_id == patient.id
    assert appt.doctor_id == doctor.id


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
