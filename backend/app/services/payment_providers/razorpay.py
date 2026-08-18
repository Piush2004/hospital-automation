"""Razorpay Test Mode via the Payment Links API.

NOTE: this has not been exercised against a real Razorpay test account
(none was available while building this) — the mock provider is what's
actually been verified end-to-end. Wire in real RAZORPAY_KEY_ID /
RAZORPAY_KEY_SECRET test keys (never live keys) and smoke-test this path
before relying on it. The interface (create_payment_link / check_status)
is what payments_agent.py depends on, so swapping providers doesn't
touch any other code — see app/services/payment_providers/base.py.

Docs: https://razorpay.com/docs/api/payments/payment-links/
"""

import logging

import httpx

from app.config import get_settings
from app.models import Appointment, Payment
from app.services.payment_providers.base import PaymentLink, PaymentOutcome, PaymentProvider

logger = logging.getLogger(__name__)

API_BASE = "https://api.razorpay.com/v1"

# Razorpay payment-link statuses that map to our three-state outcome.
_PAID_STATUSES = {"paid"}
_FAILED_STATUSES = {"cancelled", "expired"}


class RazorpayConfigError(RuntimeError):
    pass


class RazorpayPaymentProvider(PaymentProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise RazorpayConfigError(
                "MOCK_PAYMENTS=false but RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET are not set. "
                "Set test-mode keys in .env, or leave MOCK_PAYMENTS=true."
            )
        self._auth = (settings.razorpay_key_id, settings.razorpay_key_secret)

    def create_payment_link(self, payment: Payment, appointment: Appointment) -> PaymentLink:
        payload = {
            "amount": int(round(float(payment.amount) * 100)),  # paise
            "currency": payment.currency,
            "description": f"Consultation — appointment #{appointment.id}",
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {"appointment_id": str(appointment.id), "payment_id": str(payment.id)},
        }
        resp = httpx.post(f"{API_BASE}/payment_links", json=payload, auth=self._auth, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        return PaymentLink(
            reference=data["id"],
            checkout_url=data["short_url"],
            instructions="Complete payment via the secure Razorpay checkout link above.",
        )

    def check_status(self, reference: str) -> PaymentOutcome:
        resp = httpx.get(f"{API_BASE}/payment_links/{reference}", auth=self._auth, timeout=15.0)
        resp.raise_for_status()
        status = resp.json().get("status", "")
        if status in _PAID_STATUSES:
            return "paid"
        if status in _FAILED_STATUSES:
            return "failed"
        return "pending"
