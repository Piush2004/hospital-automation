"""Zero-setup payment simulation. No external account, no network call —
the "checkout" is a page our own backend serves at /pay/{reference},
where the patient (or, in a demo, the operator) explicitly marks the
payment paid or failed. See app/channels/payments_web.py for that route.
"""

import uuid

from app.config import get_settings
from app.models import Appointment, Payment
from app.services.payment_providers.base import PaymentLink, PaymentOutcome, PaymentProvider


class MockPaymentProvider(PaymentProvider):
    def create_payment_link(self, payment: Payment, appointment: Appointment) -> PaymentLink:
        reference = f"mock_{uuid.uuid4().hex[:16]}"
        base_url = get_settings().app_base_url.rstrip("/")
        checkout_url = f"{base_url}/pay/{reference}"
        instructions = (
            f"This is a demo payment - no real money moves. Open {checkout_url} to "
            "simulate completing checkout."
        )
        return PaymentLink(reference=reference, checkout_url=checkout_url, instructions=instructions)

    def check_status(self, reference: str) -> PaymentOutcome:
        # No external state to poll — the mock checkout page pushes an
        # explicit outcome via confirm_payment(..., outcome=...) instead.
        return "pending"
