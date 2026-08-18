from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus
from app.services.audit import log_action


def complete_visit(db: Session, appointment_id: int, notes: str) -> Appointment:
    """Marks a confirmed appointment as completed with visit notes attached.

    No report generation here — that's a separate, explicit step (see
    app/agents/report_agent.py) so a caller can compose them the same way
    slot_choice_node composes booking + payment-link creation: two plain
    function calls, not one function doing two things.
    """
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise ValueError(f"No appointment with id {appointment_id}")
    if appointment.status != AppointmentStatus.confirmed:
        raise ValueError(
            f"Appointment {appointment_id} is {appointment.status.value}, not confirmed - can't complete it."
        )

    appointment.status = AppointmentStatus.completed
    appointment.notes = notes
    db.flush()

    log_action(
        db,
        actor="doctor_cli",
        action="appointment.completed",
        entity_type="Appointment",
        entity_id=appointment.id,
        details={"notes_length": len(notes)},
    )
    return appointment
