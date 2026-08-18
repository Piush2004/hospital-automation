"""Orchestrator: a LangGraph supervisor that routes each conversation turn
to the right specialist node.

Design note (see CLAUDE.md working rules): this is a *per-turn* graph, not
a long-running one. A channel (CLI REPL, WebSocket, WhatsApp webhook) calls
`run_turn(db, state, user_input)` once per inbound message; the graph runs
start-to-finish and returns an updated, JSON-serializable state dict plus a
reply string. Persisting `state` (e.g. in ConversationSession.state) and
passing it back in on the next call is what makes the conversation
stateful across turns/requests without needing a live graph process or a
checkpointer.

Routing is deterministic (keyed off `stage`), not LLM-driven — reliable
control flow matters more here than flexibility, and the LLM is used
where it adds real value: symptom -> department classification in
triage_agent.

Graph shape:

    START -> emergency_check -+-> emergency_node -> END
                               +-> identify_node -> END
                               +-> triage_node -> scheduling_assign_node -> END
                               +-> slot_choice_node -> END
                               +-> awaiting_payment_node -> END
                               +-> report_consent_ask_node -> END
                               +-> report_consent_answer_node -> END
                               +-> done_node -> END

Async external events (a payment completing out-of-band on the mock/real
checkout page, a doctor finishing a visit — see payments_web.py and
doctor_cli.py) follow one pattern throughout this codebase: persist the
outcome to the DB and, if the channel is live, push a message immediately
(app/services/notifications.py); *also* leave enough state that the next
time this graph runs for that patient, it reconciles from the DB rather
than trusting only the push arrived. `awaiting_payment_node` is the first
example of that reconciliation half; `report_consent_ask_node` /
`report_consent_answer_node` are the second — a doctor completing a visit
(app/doctor_cli.py, always a separate process, never live-connected)
persists the consent question + an `awaiting_report_consent` flag
directly, and the *next* message the patient sends anywhere gets routed
into the answer node by the router below, regardless of `stage`.
"""

import logging
from datetime import datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.payments_agent import create_payment_link
from app.agents.report_agent import find_undelivered_report
from app.agents.report_delivery_agent import consent_question, decline_message, deliver_report, unclear_answer_message
from app.agents.scheduling_agent import (
    assign_doctor,
    confirm_booking,
    format_slot_options,
    parse_slot_choice,
    propose_slots,
)
from app.agents.triage_agent import classify_department
from app.llm.ollama_client import OllamaClient
from app.models import Appointment, Patient, PaymentStatus, Report
from app.services.audit import log_action
from app.services.emergency import detect_emergency
from app.services.report_requests import mentions_report_request

logger = logging.getLogger(__name__)

_YES_WORDS = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "please", "yes please"}
_NO_WORDS = {"no", "n", "nope", "not now", "no thanks", "not yet"}


class ConversationState(TypedDict, total=False):
    stage: str
    user_input: str
    reply: str

    patient_id: int
    patient_phone: str
    patient_name: str

    symptom_text: str
    department_id: int
    department_name: str
    doctor_id: int
    doctor_name: str
    candidate_slots: list[list[str]]  # [[iso_start, iso_end], ...]
    chosen_slot: list[str]
    appointment_id: int

    payment_reference: str
    payment_checkout_url: str

    awaiting_report_consent: dict | None  # {"report_id": int} while a consent question is outstanding

    is_emergency: bool


def initial_state(patient: Patient) -> tuple[ConversationState, str]:
    """Build the starting state + opening message for a brand new session."""
    known_name = bool(patient.full_name) and patient.full_name != "Unknown"
    stage = "collect_symptom" if known_name else "collect_name"
    greeting = (
        f"Hi {patient.full_name}! What's bothering you today?"
        if known_name
        else "Hi! Welcome to the clinic. Could you tell me your name?"
    )
    state: ConversationState = {
        "stage": stage,
        "patient_id": patient.id,
        "patient_phone": patient.phone,
        "patient_name": patient.full_name,
        "is_emergency": False,
    }
    return state, greeting


# --- Nodes -------------------------------------------------------------


def _emergency_check_node(state: ConversationState) -> dict:
    if detect_emergency(state.get("user_input", "")):
        return {"is_emergency": True}
    return {}


def _make_emergency_node(db: Session):
    def node(state: ConversationState) -> dict:
        log_action(
            db,
            actor="agent:orchestrator",
            action="conversation.emergency_flagged",
            entity_type="Patient",
            entity_id=state.get("patient_id"),
            details={"message": state.get("user_input")},
        )
        reply = (
            "This sounds like it could be a medical emergency. Please call your local "
            "emergency number or go to the nearest emergency room right now. "
            "I've flagged this conversation for immediate staff attention."
        )
        return {"reply": reply, "stage": "emergency"}

    return node


def _make_identify_node(db: Session):
    def node(state: ConversationState) -> dict:
        if state["stage"] == "collect_name":
            name = state["user_input"].strip()
            patient = db.get(Patient, state["patient_id"])
            patient.full_name = name or patient.full_name
            db.flush()
            return {
                "patient_name": patient.full_name,
                "stage": "collect_symptom",
                "reply": f"Thanks, {patient.full_name}! What's bothering you today?",
            }
        # Shouldn't normally be reached, but stay safe.
        return {"reply": "Could you tell me your name?", "stage": "collect_name"}

    return node


def _make_triage_node(db: Session, llm: OllamaClient):
    def node(state: ConversationState) -> dict:
        symptom_text = state["user_input"].strip()
        department = classify_department(db, symptom_text, llm=llm)
        return {
            "symptom_text": symptom_text,
            "department_id": department.id,
            "department_name": department.name,
        }

    return node


def _make_scheduling_assign_node(db: Session):
    def node(state: ConversationState) -> dict:
        department_id = state["department_id"]
        department_name = state["department_name"]
        doctor = assign_doctor(db, department_id)

        if doctor is None:
            return {
                "reply": (
                    f"I couldn't find an available doctor in {department_name} right now. "
                    "Please contact the front desk directly."
                ),
                "stage": "collect_symptom",
            }

        slots = propose_slots(db, doctor.id)
        if not slots:
            return {
                "doctor_id": doctor.id,
                "doctor_name": doctor.full_name,
                "reply": (
                    f"{doctor.full_name} ({department_name}) doesn't have any openings in the next "
                    "two weeks. Please contact the front desk directly."
                ),
                "stage": "done",
            }

        options_text = format_slot_options(slots)
        reply = (
            f"Based on what you've described, I'm connecting you with {doctor.full_name} "
            f"({department_name}). Here are the next available slots:\n{options_text}\n"
            "Reply with a number to book."
        )
        return {
            "doctor_id": doctor.id,
            "doctor_name": doctor.full_name,
            "candidate_slots": [[s.isoformat(), e.isoformat()] for s, e in slots],
            "reply": reply,
            "stage": "choose_slot",
        }

    return node


def _make_slot_choice_node(db: Session):
    def node(state: ConversationState) -> dict:
        raw_slots = state.get("candidate_slots", [])
        slots = [(datetime.fromisoformat(s), datetime.fromisoformat(e)) for s, e in raw_slots]
        choice = parse_slot_choice(state["user_input"], slots)

        if choice is None:
            return {
                "reply": f"Sorry, please reply with a number from 1 to {len(slots)}.",
                "stage": "choose_slot",
            }

        patient = db.get(Patient, state["patient_id"])
        doctor_id = state["doctor_id"]
        from app.models import Doctor  # local import to avoid cycle at module load

        doctor = db.get(Doctor, doctor_id)
        appointment = confirm_booking(db, patient, doctor, choice, reason=state.get("symptom_text"))

        payment, link = create_payment_link(db, appointment)

        slot_start, _slot_end = choice
        reply = (
            f"You're provisionally booked with {doctor.full_name} on "
            f"{slot_start.strftime('%A %d %B, %H:%M')} UTC. To confirm, please pay "
            f"{payment.currency} {payment.amount}: {link.checkout_url}\n{link.instructions}"
        )
        return {
            "chosen_slot": [choice[0].isoformat(), choice[1].isoformat()],
            "appointment_id": appointment.id,
            "payment_reference": link.reference,
            "payment_checkout_url": link.checkout_url,
            "reply": reply,
            "stage": "await_payment",
        }

    return node


def _make_awaiting_payment_node(db: Session):
    def node(state: ConversationState) -> dict:
        appointment = db.get(Appointment, state["appointment_id"])
        payment = appointment.payment

        if payment.status == PaymentStatus.paid:
            return {
                "reply": (
                    f"You're already confirmed with {appointment.doctor.full_name} on "
                    f"{appointment.slot_start.strftime('%A %d %B, %H:%M')} UTC. "
                    "Anything else I can help with?"
                ),
                "stage": "done",
            }

        if payment.status == PaymentStatus.failed:
            _payment, link = create_payment_link(db, appointment)
            return {
                "payment_reference": link.reference,
                "payment_checkout_url": link.checkout_url,
                "reply": (
                    f"That payment didn't go through. Here's a fresh link: {link.checkout_url}\n"
                    f"{link.instructions}"
                ),
                "stage": "await_payment",
            }

        checkout_url = state.get("payment_checkout_url", "")
        return {
            "reply": f"Still waiting on payment. Use this link when you're ready: {checkout_url}",
            "stage": "await_payment",
        }

    return node


def _make_report_consent_ask_node(db: Session):
    def node(state: ConversationState) -> dict:
        report = find_undelivered_report(db, state["patient_id"])
        if report is None:
            # Shouldn't happen (the router only sends us here when one
            # exists), but stay safe rather than crash the turn.
            return {"reply": "I don't see a report waiting for you right now."}
        return {
            "awaiting_report_consent": {"report_id": report.id},
            "reply": consent_question(report),
        }

    return node


def _make_report_consent_answer_node(db: Session):
    def node(state: ConversationState) -> dict:
        info = state["awaiting_report_consent"]
        report = db.get(Report, info["report_id"])
        answer = state["user_input"].strip().lower()

        if answer in _YES_WORDS:
            reply = deliver_report(db, report)
            return {"reply": reply, "awaiting_report_consent": None}
        if answer in _NO_WORDS:
            return {"reply": decline_message(), "awaiting_report_consent": None}
        return {"reply": unclear_answer_message()}

    return node


def _done_node(state: ConversationState) -> dict:
    return {"reply": "You're all set - is there anything else I can help you with?"}


# --- Graph construction --------------------------------------------------


def _make_router(db: Session):
    def route(state: ConversationState) -> str:
        if state.get("is_emergency"):
            return "emergency"
        if state.get("awaiting_report_consent"):
            return "report_consent_answer"
        if mentions_report_request(state.get("user_input", "")) and find_undelivered_report(
            db, state["patient_id"]
        ):
            return "report_consent_ask"
        return {
            "collect_name": "identify",
            "collect_symptom": "triage",
            "choose_slot": "slot_choice",
            "await_payment": "awaiting_payment",
            "done": "done",
            "emergency": "emergency",
        }.get(state["stage"], "identify")

    return route


def build_graph(db: Session, llm: OllamaClient | None = None):
    llm = llm or OllamaClient()
    graph = StateGraph(ConversationState)

    graph.add_node("emergency_check", _emergency_check_node)
    graph.add_node("emergency_node", _make_emergency_node(db))
    graph.add_node("identify_node", _make_identify_node(db))
    graph.add_node("triage_node", _make_triage_node(db, llm))
    graph.add_node("scheduling_assign_node", _make_scheduling_assign_node(db))
    graph.add_node("slot_choice_node", _make_slot_choice_node(db))
    graph.add_node("awaiting_payment_node", _make_awaiting_payment_node(db))
    graph.add_node("report_consent_ask_node", _make_report_consent_ask_node(db))
    graph.add_node("report_consent_answer_node", _make_report_consent_answer_node(db))
    graph.add_node("done_node", _done_node)

    graph.add_edge(START, "emergency_check")
    graph.add_conditional_edges(
        "emergency_check",
        _make_router(db),
        {
            "emergency": "emergency_node",
            "identify": "identify_node",
            "triage": "triage_node",
            "slot_choice": "slot_choice_node",
            "awaiting_payment": "awaiting_payment_node",
            "report_consent_ask": "report_consent_ask_node",
            "report_consent_answer": "report_consent_answer_node",
            "done": "done_node",
        },
    )
    graph.add_edge("emergency_node", END)
    graph.add_edge("identify_node", END)
    graph.add_edge("triage_node", "scheduling_assign_node")
    graph.add_edge("scheduling_assign_node", END)
    graph.add_edge("slot_choice_node", END)
    graph.add_edge("awaiting_payment_node", END)
    graph.add_edge("report_consent_ask_node", END)
    graph.add_edge("report_consent_answer_node", END)
    graph.add_edge("done_node", END)

    return graph.compile()


def run_turn(db: Session, state: ConversationState, user_input: str, llm: OllamaClient | None = None) -> tuple[ConversationState, str]:
    """Run one conversation turn. Returns (updated_state, reply_text).

    `state` is mutated-and-returned as a plain dict so callers can persist
    it directly into ConversationSession.state (a JSON column).
    """
    app = build_graph(db, llm=llm)
    input_state: ConversationState = {**state, "user_input": user_input}
    result = app.invoke(input_state)

    reply = result.pop("reply", "")
    result.pop("user_input", None)
    return result, reply
