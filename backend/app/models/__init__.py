"""Import every model so Base.metadata is fully populated (for Alembic
autogenerate) and SQLAlchemy can resolve string-based relationship()
forward references against the declarative registry.
"""

from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.conversation import ConversationSession
from app.models.department import Department
from app.models.doctor import Doctor, DoctorAvailability
from app.models.enums import (
    AppointmentStatus,
    ConversationChannel,
    ConversationStatus,
    DeliveryChannel,
    PaymentStatus,
    UserRole,
)
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.report import Report
from app.models.user import User

__all__ = [
    "Appointment",
    "AppointmentStatus",
    "AuditLog",
    "ConversationChannel",
    "ConversationSession",
    "ConversationStatus",
    "DeliveryChannel",
    "Department",
    "Doctor",
    "DoctorAvailability",
    "Patient",
    "Payment",
    "PaymentStatus",
    "Report",
    "User",
    "UserRole",
]
