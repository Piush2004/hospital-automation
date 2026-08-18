from datetime import datetime, timezone

from app.agents.orchestrator import initial_state, run_turn
from app.models import Appointment, AppointmentStatus, Department, Doctor, Patient, Report


class _StubLLM:
    def chat_json(self, messages, temperature=0.1, retries=2):
        return {"department": "General Medicine", "reasoning": "n/a"}


def _seed_report(db, notes: str = "Rest and fluids.") -> Report:
    dept = Department(name="General Medicine")
    db.add(dept)
    db.flush()
    doctor = Doctor(full_name="Dr. Notes", specialty="GP", department_id=dept.id)
    db.add(doctor)
    db.flush()
    patient = Patient(full_name="Consent Pat", phone="+1700")
    db.add(patient)
    db.flush()
    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        slot_start=datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc),
        slot_end=datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc),
        status=AppointmentStatus.completed,
        notes=notes,
    )
    db.add(appointment)
    db.flush()
    report = Report(
        appointment_id=appointment.id,
        file_path="/tmp/does-not-need-to-exist.pdf",
        generated_at=datetime.now(timezone.utc),
    )
    db.add(report)
    db.flush()
    return report


def test_saying_yes_delivers_and_records_consent(db):
    report = _seed_report(db)
    patient = report.appointment.patient
    llm = _StubLLM()

    state, _greeting = initial_state(patient)
    state["awaiting_report_consent"] = {"report_id": report.id}

    state, reply = run_turn(db, state, "yes", llm=llm)

    db.refresh(report)
    assert report.consent_at is not None
    assert report.delivered_at is not None
    assert f"/reports/{report.id}/download" in reply
    assert state.get("awaiting_report_consent") is None


def test_saying_no_declines_without_consent(db):
    report = _seed_report(db)
    patient = report.appointment.patient
    llm = _StubLLM()

    state, _greeting = initial_state(patient)
    state["awaiting_report_consent"] = {"report_id": report.id}

    state, reply = run_turn(db, state, "no thanks", llm=llm)

    db.refresh(report)
    assert report.consent_at is None
    assert "no problem" in reply.lower()
    assert state.get("awaiting_report_consent") is None


def test_unclear_answer_reprompts_and_keeps_waiting(db):
    report = _seed_report(db)
    patient = report.appointment.patient
    llm = _StubLLM()

    state, _greeting = initial_state(patient)
    state["awaiting_report_consent"] = {"report_id": report.id}

    state, reply = run_turn(db, state, "maybe later idk", llm=llm)

    assert state.get("awaiting_report_consent") == {"report_id": report.id}
    assert "yes/no" in reply.lower() or "yes" in reply.lower()


def test_keyword_trigger_asks_for_undelivered_report(db):
    report = _seed_report(db)
    patient = report.appointment.patient
    llm = _StubLLM()

    state, _greeting = initial_state(patient)
    assert "awaiting_report_consent" not in state or not state.get("awaiting_report_consent")

    state, reply = run_turn(db, state, "can I get my report please", llm=llm)

    assert state.get("awaiting_report_consent") == {"report_id": report.id}
    assert "report" in reply.lower()

    # Follow-up should now be interpreted as the consent answer, not a symptom.
    state, reply = run_turn(db, state, "yes", llm=llm)
    db.refresh(report)
    assert report.consent_at is not None


def test_no_report_keyword_without_pending_report_falls_through_to_normal_routing(db):
    dept = Department(name="General Medicine")
    db.add(dept)
    db.flush()
    patient = Patient(full_name="No Report Pat", phone="+1701")
    db.add(patient)
    db.flush()

    llm = _StubLLM()
    state, _greeting = initial_state(patient)

    # Mentions "report" but there's no undelivered report for this patient -
    # should just be treated as ordinary symptom text, not intercepted.
    # (No doctor seeded in this department, so triage runs but scheduling
    # can't assign one - stage stays put. The point being tested is that
    # it reaches triage/scheduling at all, not the emergency/report path.)
    state, reply = run_turn(db, state, "my report of symptoms: fever and my report is bad", llm=llm)

    assert not state.get("awaiting_report_consent")
    assert state["stage"] == "collect_symptom"
    assert "department_name" in state  # triage ran
