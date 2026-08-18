"""WhatsApp channel: a thin FastAPI adapter over the same `run_turn()`
orchestrator every other channel uses - see app/channels/web_chat.py for
the pattern this mirrors. The actual WhatsApp connection lives in the
separate whatsapp-gateway/ Node process (Baileys, unofficial protocol -
see README's ToS caveat); this endpoint is what it POSTs inbound
messages to.

Unlike web_chat's websocket, this is a plain synchronous request/response:
the gateway sends {phone, message, secret}, waits for this endpoint to
run one orchestrator turn, and gets {reply} back to relay over its
Baileys socket. No live-connection registry needed for the inbound path -
see app/services/whatsapp_client.py for how the *outbound*/proactive path
works instead.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.orchestrator import initial_state, run_turn
from app.config import get_settings
from app.db import SessionLocal
from app.llm.ollama_client import OllamaClient
from app.models import ConversationChannel
from app.services.conversations import append_history, create_session, get_active_session, save_state
from app.services.patients import get_or_create_patient

logger = logging.getLogger(__name__)
router = APIRouter()

_llm = OllamaClient()


class WhatsAppInbound(BaseModel):
    phone: str
    message: str
    secret: str


@router.post("/webhook/whatsapp")
def whatsapp_webhook(payload: WhatsAppInbound) -> dict:
    settings = get_settings()
    if payload.secret != settings.whatsapp_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    if not payload.message.strip():
        return {"reply": ""}

    db = SessionLocal()
    try:
        patient = get_or_create_patient(db, payload.phone)
        session = get_active_session(db, ConversationChannel.whatsapp, payload.phone)

        if session is None:
            # Unlike web_chat's websocket, there's no separate "connect"
            # event to proactively push a greeting through - the first
            # inbound message IS the connect event. Reply with just the
            # greeting and treat whatever they actually typed as a wake-up
            # ping rather than guessing whether it was meant to answer a
            # question they hadn't been asked yet; their real first answer
            # is their *next* message, same as every other channel.
            state, greeting = initial_state(patient)
            session = create_session(db, ConversationChannel.whatsapp, payload.phone, patient.id, state)
            append_history(session, "user", payload.message)
            append_history(session, "assistant", greeting)
            db.commit()
            return {"reply": greeting}

        state = session.state
        append_history(session, "user", payload.message)
        new_state, reply = run_turn(db, state, payload.message, llm=_llm)
        save_state(session, new_state, is_emergency=new_state.get("is_emergency", False))
        append_history(session, "assistant", reply)
        db.commit()

        return {"reply": reply}
    finally:
        db.close()
