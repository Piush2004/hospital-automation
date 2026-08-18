import enum


class UserRole(str, enum.Enum):
    patient = "patient"
    doctor = "doctor"
    front_desk = "front_desk"
    admin = "admin"


class AppointmentStatus(str, enum.Enum):
    requested = "requested"
    pending_payment = "pending_payment"
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"
    no_show = "no_show"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"


class ConversationChannel(str, enum.Enum):
    web_chat = "web_chat"
    whatsapp = "whatsapp"
    voice = "voice"


class ConversationStatus(str, enum.Enum):
    active = "active"
    closed = "closed"
    escalated = "escalated"


class DeliveryChannel(str, enum.Enum):
    chat = "chat"
    email = "email"
