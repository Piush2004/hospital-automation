"""Admin/front-desk dashboard: appointments table, a doctor-calendar
view (appointments grouped by doctor — a grouped list, not a real
calendar widget; MVP scope), an audit log viewer, and an emergency
inbox surfacing the fast-path trigger events from orchestrator.py's
emergency_node to an actual human. All read-mostly except acknowledging
an emergency.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Appointment,
    AuditLog,
    ConversationSession,
    ConversationStatus,
    Doctor,
    User,
    UserRole,
)
from app.services.audit import log_action
from app.services.auth import require_roles

router = APIRouter(prefix="/api/admin", tags=["admin"])

_STAFF = (UserRole.front_desk, UserRole.admin)


class AppointmentRow(BaseModel):
    id: int
    patient_name: str
    patient_phone: str
    doctor_name: str
    department_name: str
    slot_start: datetime
    slot_end: datetime
    status: str
    reason: str | None = None


class DoctorCalendarEntry(BaseModel):
    doctor_id: int
    doctor_name: str
    department_name: str
    appointments: list[AppointmentRow]


class AuditLogRow(BaseModel):
    id: int
    actor: str
    action: str
    entity_type: str
    entity_id: str | None = None
    details: dict | None = None
    timestamp: datetime


class EmergencyRow(BaseModel):
    session_id: int
    channel: str
    patient_name: str | None = None
    patient_phone: str | None = None
    last_message: str | None = None
    flagged_at: datetime
    status: str


def _appointment_row(a: Appointment) -> AppointmentRow:
    return AppointmentRow(
        id=a.id,
        patient_name=a.patient.full_name,
        patient_phone=a.patient.phone,
        doctor_name=a.doctor.full_name,
        department_name=a.doctor.department.name,
        slot_start=a.slot_start,
        slot_end=a.slot_end,
        status=a.status.value,
        reason=a.reason,
    )


@router.get("/appointments", response_model=list[AppointmentRow])
def list_appointments(
    status_filter: str | None = Query(None, alias="status"),
    doctor_id: int | None = None,
    _user: User = Depends(require_roles(*_STAFF)),
    db: Session = Depends(get_db),
) -> list[AppointmentRow]:
    query = db.query(Appointment)
    if status_filter:
        query = query.filter(Appointment.status == status_filter)
    if doctor_id:
        query = query.filter(Appointment.doctor_id == doctor_id)
    appointments = query.order_by(Appointment.slot_start.desc()).limit(500).all()
    return [_appointment_row(a) for a in appointments]


@router.get("/doctors/calendar", response_model=list[DoctorCalendarEntry])
def doctor_calendar(_user: User = Depends(require_roles(*_STAFF)), db: Session = Depends(get_db)) -> list[DoctorCalendarEntry]:
    doctors = db.query(Doctor).filter_by(is_active=True).order_by(Doctor.full_name).all()
    entries = []
    for doctor in doctors:
        appointments = (
            db.query(Appointment)
            .filter(Appointment.doctor_id == doctor.id, Appointment.status.in_(["confirmed", "pending_payment"]))
            .order_by(Appointment.slot_start)
            .all()
        )
        entries.append(
            DoctorCalendarEntry(
                doctor_id=doctor.id,
                doctor_name=doctor.full_name,
                department_name=doctor.department.name,
                appointments=[_appointment_row(a) for a in appointments],
            )
        )
    return entries


@router.get("/audit-log", response_model=list[AuditLogRow])
def audit_log(
    limit: int = Query(100, le=500),
    offset: int = 0,
    action: str | None = None,
    _user: User = Depends(require_roles(*_STAFF)),
    db: Session = Depends(get_db),
) -> list[AuditLogRow]:
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    rows = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()
    return [
        AuditLogRow(
            id=r.id,
            actor=r.actor,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            details=r.details,
            timestamp=r.timestamp,
        )
        for r in rows
    ]


@router.get("/emergencies", response_model=list[EmergencyRow])
def emergencies(_user: User = Depends(require_roles(*_STAFF)), db: Session = Depends(get_db)) -> list[EmergencyRow]:
    sessions = (
        db.query(ConversationSession)
        .filter_by(is_emergency=True)
        .order_by(ConversationSession.updated_at.desc())
        .all()
    )
    return [
        EmergencyRow(
            session_id=s.id,
            channel=s.channel.value,
            patient_name=s.patient.full_name if s.patient else None,
            patient_phone=s.patient.phone if s.patient else s.external_id,
            last_message=s.history[-1]["content"] if s.history else None,
            flagged_at=s.updated_at,
            status=s.status.value,
        )
        for s in sessions
    ]


@router.post("/emergencies/{session_id}/acknowledge")
def acknowledge_emergency(
    session_id: int, user: User = Depends(require_roles(*_STAFF)), db: Session = Depends(get_db)
) -> dict:
    session = db.get(ConversationSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session.status = ConversationStatus.closed
    log_action(
        db,
        actor=f"user:{user.id}",
        action="emergency.acknowledged",
        entity_type="ConversationSession",
        entity_id=session.id,
    )
    db.commit()
    return {"ok": True}
