"""Optional email delivery via plain SMTP (e.g. Gmail SMTP if the user
supplies credentials — never required). Only ever called when
SMTP_ENABLED=true and the caller has already decided to send; see
app/agents/report_delivery_agent.py, which wraps this in a try/except so
a misconfigured or unreachable SMTP server never blocks the chat-based
delivery that already happened.

NOTE: unverified — no SMTP account was configured while building this.
The rest of the app has zero dependency on this path working.
"""

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from app.config import get_settings
from app.models import Report


def send_report_email(to_email: str, report: Report) -> None:
    settings = get_settings()
    appointment = report.appointment

    msg = MIMEMultipart()
    msg["Subject"] = "Your visit report"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email

    body = (
        f"Hi {appointment.patient.full_name},\n\n"
        f"Attached is your visit report from {appointment.doctor.full_name} "
        f"on {appointment.slot_start.strftime('%A %d %B %Y')}.\n\n"
        "This is an automated message from the clinic's local demo system."
    )
    msg.attach(MIMEText(body, "plain"))

    pdf_path = Path(report.file_path)
    if pdf_path.exists():
        with open(pdf_path, "rb") as f:
            attachment = MIMEApplication(f.read(), _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
        msg.attach(attachment)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
