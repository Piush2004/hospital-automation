"""Report Delivery agent.

Nothing gets sent without an explicit yes from the patient in chat —
`deliver_report` is only ever called after that consent is captured (see
the report_consent_answer_node wiring in app/agents/orchestrator.py).
Consent is recorded on the Report row itself (`consent_at`), not just
implied by the delivery happening, so it's independently auditable.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DeliveryChannel, Report
from app.services.audit import log_action

logger = logging.getLogger(__name__)


def consent_question(report: Report) -> str:
    appointment = report.appointment
    return (
        f"Your visit report from {appointment.doctor.full_name} on "
        f"{appointment.slot_start.strftime('%A %d %B')} is ready. "
        "Would you like it sent here now? (yes/no)"
    )


def decline_message() -> str:
    return "No problem - just say something like 'send my report' whenever you're ready."


def unclear_answer_message() -> str:
    return "Sorry, just to confirm - would you like your report sent here now? (yes/no)"


def deliver_report(db: Session, report: Report) -> str:
    """Records consent + delivery, attempts an optional email send (best
    effort, never blocks chat delivery), and returns the reply text.
    """
    now = datetime.now(timezone.utc)
    report.consent_at = now
    report.delivered_at = now
    report.delivery_channel = DeliveryChannel.chat
    db.flush()

    log_action(
        db,
        actor="agent:report_delivery",
        action="report.delivered",
        entity_type="Report",
        entity_id=report.id,
        details={"channel": "chat"},
    )

    settings = get_settings()
    download_url = f"{settings.app_base_url.rstrip('/')}/reports/{report.id}/download"
    reply = f"Here's your report: {download_url}"

    patient = report.appointment.patient
    if settings.smtp_enabled and patient.email:
        try:
            from app.services.email import send_report_email

            send_report_email(patient.email, report)
            log_action(
                db, actor="agent:report_delivery", action="report.emailed", entity_type="Report", entity_id=report.id
            )
            reply += f" (also emailed to {patient.email})"
        except Exception:
            logger.warning("Email delivery failed for report %s", report.id, exc_info=True)

    return reply
