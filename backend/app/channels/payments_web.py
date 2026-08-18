"""Mock checkout page: GET /pay/{reference} renders a tiny HTML page with
Paid/Failed buttons, POST /pay/{reference}/complete resolves the payment
via payments_agent.confirm_payment and — if paid — pushes a confirmation
back into the patient's chat (live if connected, persisted either way).

Only serves `provider == "mock"` payments. A real Razorpay payment link
points the patient at Razorpay's own hosted checkout instead; this route
never comes into play for that path.
"""

import asyncio

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse

from app.agents.payments_agent import confirm_payment
from app.db import SessionLocal
from app.models import Payment
from app.services import notifications

router = APIRouter()


def _confirmation_message(payment: Payment) -> str:
    appointment = payment.appointment
    doctor = appointment.doctor
    return (
        f"Payment received for your appointment with {doctor.full_name} on "
        f"{appointment.slot_start.strftime('%A %d %B, %H:%M')} UTC - you're confirmed!"
    )


def _failure_message(payment: Payment) -> str:
    appointment = payment.appointment
    return (
        "That payment didn't go through. Send another message in chat whenever "
        "you're ready and I'll generate a fresh payment link for your "
        f"appointment with {appointment.doctor.full_name}."
    )


@router.get("/pay/{reference}", response_class=HTMLResponse)
def pay_page(reference: str) -> str:
    db = SessionLocal()
    try:
        payment = db.query(Payment).filter_by(provider_ref=reference).one_or_none()
        if payment is None or payment.provider != "mock":
            raise HTTPException(status_code=404, detail="Payment not found")

        appointment = payment.appointment
        if payment.status.value != "pending":
            return f"""
            <html><body style="font-family: sans-serif; max-width: 480px; margin: 60px auto;">
            <h2>Payment {payment.status.value}</h2>
            <p>This payment has already been marked <strong>{payment.status.value}</strong>.</p>
            </body></html>
            """

        return f"""
        <html><body style="font-family: sans-serif; max-width: 480px; margin: 60px auto;">
        <h2>Demo Checkout</h2>
        <p>No real money moves - this simulates a payment gateway for local testing.</p>
        <p><strong>Doctor:</strong> {appointment.doctor.full_name}<br>
        <strong>Amount:</strong> {payment.currency} {payment.amount}</p>
        <form method="post" action="/pay/{reference}/complete" style="display:inline;">
          <input type="hidden" name="outcome" value="paid">
          <button type="submit" style="padding:10px 16px;background:#16a34a;color:white;border:none;border-radius:6px;cursor:pointer;">Mark as Paid</button>
        </form>
        <form method="post" action="/pay/{reference}/complete" style="display:inline; margin-left:8px;">
          <input type="hidden" name="outcome" value="failed">
          <button type="submit" style="padding:10px 16px;background:#dc2626;color:white;border:none;border-radius:6px;cursor:pointer;">Mark as Failed</button>
        </form>
        </body></html>
        """
    finally:
        db.close()


@router.post("/pay/{reference}/complete", response_class=HTMLResponse)
async def pay_complete(reference: str, outcome: str = Form(...)) -> str:
    if outcome not in ("paid", "failed"):
        raise HTTPException(status_code=400, detail="outcome must be 'paid' or 'failed'")

    db = SessionLocal()

    def resolve_payment():
        # Sync DB work, offloaded to a thread so it doesn't block the
        # event loop - same rationale as web_chat.py's fix (this one's
        # window is much smaller with no LLM call involved, but the
        # category of bug is identical, so fixed the same way).
        payment = db.query(Payment).filter_by(provider_ref=reference).one_or_none()
        if payment is None or payment.provider != "mock":
            raise HTTPException(status_code=404, detail="Payment not found")

        payment = confirm_payment(db, reference, outcome=outcome)
        db.commit()

        message = _confirmation_message(payment) if outcome == "paid" else _failure_message(payment)
        state_update = {"stage": "done"} if outcome == "paid" else None
        sessions = notifications.queue_message_for_patient(
            db, payment.appointment.patient_id, message, state_update=state_update
        )
        return message, sessions

    try:
        message, sessions = await asyncio.to_thread(resolve_payment)
        await notifications.push_live(sessions)

        return f"""
        <html><body style="font-family: sans-serif; max-width: 480px; margin: 60px auto;">
        <h2>{"Payment received" if outcome == "paid" else "Payment failed"}</h2>
        <p>{message}</p>
        <p>You can close this tab and return to the chat.</p>
        </body></html>
        """
    finally:
        db.close()
