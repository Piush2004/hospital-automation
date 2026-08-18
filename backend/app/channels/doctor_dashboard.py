"""Doctor dashboard: the auth-gated replacement for doctor_cli.py's role.
Same underlying service calls (complete_visit, generate_report, consent
queueing) — see app/doctor_cli.py, which is kept around as a scriptable
fallback (handy for demo_walkthrough.py) but is no longer the primary
way a doctor completes a visit day to day.

Scoped to the logged-in doctor's own appointments only — doctor_cli.py
originally listed every doctor's confirmed appointments (it had no
identity to scope by); real auth makes that scoping the obvious
improvement, not just a nice-to-have.

Runs inside the same FastAPI process as everything else, so the
consent-question push to the patient's live channel happens as a direct
`await notifications.push_live(...)` call — no HTTP hop needed. Compare
to doctor_cli.py, a genuinely separate process, which has to go through
POST /internal/push-live instead (see app/channels/internal.py).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.report_agent import generate_report
from app.agents.report_delivery_agent import consent_question
from app.db import get_db
from app.models import Appointment, AppointmentStatus, Doctor, User, UserRole
from app.services import notifications
from app.services.appointments import complete_visit
from app.services.auth import require_roles

router = APIRouter(prefix="/api/doctor", tags=["doctor"])


class AppointmentSummary(BaseModel):
    id: int
    patient_name: str
    patient_phone: str
    slot_start: datetime
    slot_end: datetime
    status: str
    reason: str | None = None


class CompleteVisitRequest(BaseModel):
    notes: str


class CompleteVisitResponse(BaseModel):
    appointment_id: int
    report_id: int
    report_file_path: str
    sessions_notified: int


def _get_own_doctor(user: User, db: Session) -> Doctor:
    doctor = db.query(Doctor).filter_by(user_id=user.id).one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account isn't linked to a doctor profile.",
        )
    return doctor


@router.get("/appointments", response_model=list[AppointmentSummary])
def list_my_appointments(
    user: User = Depends(require_roles(UserRole.doctor)), db: Session = Depends(get_db)
) -> list[AppointmentSummary]:
    doctor = _get_own_doctor(user, db)
    appointments = (
        db.query(Appointment)
        .filter_by(doctor_id=doctor.id, status=AppointmentStatus.confirmed)
        .order_by(Appointment.slot_start)
        .all()
    )
    return [
        AppointmentSummary(
            id=a.id,
            patient_name=a.patient.full_name,
            patient_phone=a.patient.phone,
            slot_start=a.slot_start,
            slot_end=a.slot_end,
            status=a.status.value,
            reason=a.reason,
        )
        for a in appointments
    ]


@router.post("/appointments/{appointment_id}/complete", response_model=CompleteVisitResponse)
async def complete_appointment(
    appointment_id: int,
    payload: CompleteVisitRequest,
    user: User = Depends(require_roles(UserRole.doctor)),
    db: Session = Depends(get_db),
) -> CompleteVisitResponse:
    doctor = _get_own_doctor(user, db)

    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    if appointment.doctor_id != doctor.id:
        # Not this doctor's appointment - 404, not 403, so the dashboard
        # doesn't leak which appointment ids belong to other doctors.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    appointment = complete_visit(db, appointment_id, payload.notes, actor=f"user:{user.id}")
    report = generate_report(db, appointment)
    db.commit()

    question = consent_question(report)
    sessions = notifications.queue_message_for_patient(
        db, appointment.patient_id, question, state_update={"awaiting_report_consent": {"report_id": report.id}}
    )
    db.commit()
    await notifications.push_live(sessions)

    return CompleteVisitResponse(
        appointment_id=appointment.id,
        report_id=report.id,
        report_file_path=report.file_path,
        sessions_notified=len(sessions),
    )
