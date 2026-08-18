"""Payments & Billing agent.

Single interface (`create_payment_link`, `confirm_payment`) over two
backends selected by `MOCK_PAYMENTS` — see
app/services/payment_providers/base.py for why that split exists and
app/services/payment_providers/{mock,razorpay}.py for the implementations.

Not LLM-based, deliberately: this is a state-transition problem
(pending -> paid/failed -> appointment confirmed), not a language
problem. Consistent with the rest of this codebase's rule that the local
model is used only where free-text understanding is actually needed.

One Payment row per Appointment (schema has a unique constraint on
appointment_id — see app/models/payment.py). A failed attempt is retried
by regenerating the link on the *same* row via `create_payment_link`
rather than inserting a new one.
"""

from app.config import get_settings
from app.models import Appointment, AppointmentStatus, Payment, PaymentStatus
from app.services.audit import log_action
from app.services.payment_providers.base import PaymentLink, PaymentOutcome, PaymentProvider
from app.services.payment_providers.mock import MockPaymentProvider
from app.services.payment_providers.razorpay import RazorpayPaymentProvider
from sqlalchemy.orm import Session


def get_provider() -> PaymentProvider:
    settings = get_settings()
    if settings.mock_payments:
        return MockPaymentProvider()
    return RazorpayPaymentProvider()


def _provider_label(provider: PaymentProvider) -> str:
    return "mock" if isinstance(provider, MockPaymentProvider) else "razorpay"


def _get_or_create_payment(db: Session, appointment: Appointment) -> Payment:
    payment = db.query(Payment).filter_by(appointment_id=appointment.id).one_or_none()
    if payment is None:
        payment = Payment(
            appointment_id=appointment.id,
            amount=appointment.doctor.consultation_fee,
            currency="INR",
            status=PaymentStatus.pending,
        )
        db.add(payment)
        db.flush()
    return payment


def create_payment_link(db: Session, appointment: Appointment) -> tuple[Payment, PaymentLink]:
    """Creates (or regenerates, if this is a retry) a payment link for an
    appointment. Does not itself change appointment status — that only
    happens once `confirm_payment` sees a "paid" outcome.
    """
    provider = get_provider()
    payment = _get_or_create_payment(db, appointment)
    payment.status = PaymentStatus.pending
    payment.provider = _provider_label(provider)

    link = provider.create_payment_link(payment, appointment)
    payment.provider_ref = link.reference
    db.flush()

    log_action(
        db,
        actor="agent:payments",
        action="payment.link_created",
        entity_type="Payment",
        entity_id=payment.id,
        details={"appointment_id": appointment.id, "provider": payment.provider, "reference": link.reference},
    )
    return payment, link


def confirm_payment(db: Session, reference: str, outcome: PaymentOutcome | None = None) -> Payment:
    """Resolves a payment by provider reference.

    `outcome`, when given, is an explicit signal (e.g. the mock checkout
    page's Paid/Failed button). When omitted, the provider is asked for
    the real current status — this is the reconciliation path for a real
    gateway with no webhook wired up (see CLAUDE.md deviations).
    """
    payment = db.query(Payment).filter_by(provider_ref=reference).one_or_none()
    if payment is None:
        raise ValueError(f"No payment found for reference {reference!r}")

    provider = get_provider()
    final_outcome = outcome or provider.check_status(reference)

    if final_outcome == "paid" and payment.status != PaymentStatus.paid:
        payment.status = PaymentStatus.paid
        appointment = payment.appointment
        appointment.status = AppointmentStatus.confirmed
        log_action(
            db,
            actor="agent:payments",
            action="payment.paid",
            entity_type="Payment",
            entity_id=payment.id,
            details={"appointment_id": appointment.id, "amount": str(payment.amount)},
        )
        log_action(
            db,
            actor="agent:payments",
            action="appointment.confirmed",
            entity_type="Appointment",
            entity_id=appointment.id,
        )
    elif final_outcome == "failed" and payment.status != PaymentStatus.failed:
        payment.status = PaymentStatus.failed
        log_action(
            db,
            actor="agent:payments",
            action="payment.failed",
            entity_type="Payment",
            entity_id=payment.id,
            details={"appointment_id": payment.appointment_id},
        )

    db.flush()
    return payment
