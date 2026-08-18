"""Report Generation agent.

Compiles a simple one-page PDF from an already-completed appointment
(see app/services/appointments.py:complete_visit for how it gets to
`completed`). Not LLM-based — this is a data-to-PDF formatting problem,
not a language-understanding one.
"""

from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Appointment, Report
from app.services.audit import log_action


def find_undelivered_report(db: Session, patient_id: int) -> Report | None:
    """Most recent generated-but-not-yet-consented-to report for a patient,
    if any. Used both for the proactive ask (right after a doctor
    completes a visit) and the reactive one (patient says "send my
    report" after having declined, or after missing the proactive push).
    """
    return (
        db.query(Report)
        .join(Appointment)
        .filter(Appointment.patient_id == patient_id, Report.consent_at.is_(None))
        .order_by(Report.generated_at.desc())
        .first()
    )


def _render_pdf(appointment: Appointment, file_path: str) -> None:
    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4
    left = 2 * cm
    y = height - 2.5 * cm

    def line(text: str, size: int = 11, gap: float = 0.7 * cm, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(left, y, text)
        y -= gap

    line("Visit Report", size=18, bold=True, gap=1.2 * cm)
    line(f"Patient: {appointment.patient.full_name}")
    line(f"Doctor: {appointment.doctor.full_name} ({appointment.doctor.specialty})")
    line(f"Department: {appointment.doctor.department.name}")
    line(f"Visit date: {appointment.slot_start.strftime('%A %d %B %Y, %H:%M')} UTC")
    if appointment.reason:
        line(f"Reason for visit: {appointment.reason}")
    y -= 0.4 * cm
    line("Notes:", bold=True)

    # Simple word-wrap for the notes block — no need for reportlab's
    # heavier platypus layout engine for one field on a one-pager.
    max_chars_per_line = 90
    words = (appointment.notes or "").split()
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars_per_line:
            line(current)
            current = word
        else:
            current = candidate
    if current:
        line(current)

    c.showPage()
    c.save()


def generate_report(db: Session, appointment: Appointment) -> Report:
    """Creates (or regenerates, on re-run) the PDF + Report row for a
    completed appointment.
    """
    settings = get_settings()
    file_path = settings.reports_dir / f"appointment_{appointment.id}_report.pdf"
    _render_pdf(appointment, str(file_path))

    report = db.query(Report).filter_by(appointment_id=appointment.id).one_or_none()
    now = datetime.now(timezone.utc)
    if report is None:
        report = Report(appointment_id=appointment.id, file_path=str(file_path), generated_at=now)
        db.add(report)
    else:
        report.file_path = str(file_path)
        report.generated_at = now
    db.flush()

    log_action(
        db,
        actor="agent:report",
        action="report.generated",
        entity_type="Report",
        entity_id=report.id,
        details={"appointment_id": appointment.id, "file_path": str(file_path)},
    )
    return report
