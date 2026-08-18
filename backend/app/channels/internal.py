"""Internal-only endpoint so a separate-process tool (doctor_cli.py) can
trigger a live websocket push after writing directly to the DB.

Why this exists: doctor_cli.py already persists the consent question +
state update via notifications.queue_message_for_patient (that part needs
no server involvement, and doctor_cli keeps working standalone even if
the API isn't running). But an in-memory websocket registry only exists
inside *this* process — a separate CLI process can never reach it
directly. This one small hop lets the CLI ask the running server to
re-push whatever's already the latest persisted message for a patient's
active session(s), best-effort.

Locked down behind staff auth as of Phase 9 — doctor_cli.py now logs in
first and passes its token. The doctor *dashboard* (doctor_dashboard.py)
doesn't call this at all: it runs inside the same FastAPI process, so it
just awaits notifications.push_live() directly, no HTTP hop needed.
"""

from fastapi import APIRouter, Depends

from app.db import SessionLocal
from app.models import ConversationSession, ConversationStatus, User
from app.services import notifications
from app.services.auth import get_current_staff_user

router = APIRouter()


@router.post("/internal/push-live/{patient_id}")
async def push_live(patient_id: int, _user: User = Depends(get_current_staff_user)) -> dict:
    db = SessionLocal()
    try:
        sessions = (
            db.query(ConversationSession)
            .filter_by(patient_id=patient_id, status=ConversationStatus.active)
            .all()
        )
        await notifications.push_live(sessions)
        return {"sessions_checked": len(sessions)}
    finally:
        db.close()
