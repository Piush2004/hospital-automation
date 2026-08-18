"""Payment provider interface. Two implementations share this shape so
swapping mock -> real Razorpay test-mode keys is a one-line config change
(MOCK_PAYMENTS=false), not a code change — see
app/agents/payments_agent.py, which is the only place that picks between
them.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from app.models import Appointment, Payment

PaymentOutcome = Literal["pending", "paid", "failed"]


@dataclass
class PaymentLink:
    reference: str  # provider_ref stored on the Payment row
    checkout_url: str
    instructions: str


class PaymentProvider(ABC):
    @abstractmethod
    def create_payment_link(self, payment: Payment, appointment: Appointment) -> PaymentLink: ...

    @abstractmethod
    def check_status(self, reference: str) -> PaymentOutcome:
        """Ask the provider for the real current status of a payment.

        Used for reconciliation when we don't have an explicit outcome
        (e.g. no webhook). The mock provider has no external state of its
        own, so it always reports "pending" here — mock outcomes are set
        explicitly via the local /pay/{reference}/complete route instead.
        """
        ...
