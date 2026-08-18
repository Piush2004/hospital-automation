"""Web chat channel: a thin FastAPI WebSocket adapter over the same
`run_turn()` orchestrator the CLI REPL uses. This is the point of the
channel-agnostic core — WhatsApp (Phase 7) and voice (Phase 8) will be
similarly thin adapters, not reimplementations.

Protocol: connect to `/ws/chat?phone=<phone>`. The server immediately
sends the opening greeting (JSON: `{"role": "assistant", "content": ...}`)
for a new session, or the session's last message when resuming. From then
on, every text frame sent by the client is treated as one user message;
the server replies with one JSON frame per turn.
"""

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.agents.orchestrator import initial_state, run_turn
from app.db import SessionLocal
from app.llm.ollama_client import OllamaClient
from app.models import ConversationChannel
from app.services import live_connections
from app.services.conversations import append_history, create_session, get_active_session, save_state
from app.services.patients import get_or_create_patient

logger = logging.getLogger(__name__)
router = APIRouter()

# One client per process is plenty for a local prototype — avoids paying
# an HTTP handshake per chat turn.
_llm = OllamaClient()


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket, phone: str = Query(...)) -> None:
    await websocket.accept()
    live_connections.register(ConversationChannel.web_chat, phone, websocket)
    db = SessionLocal()

    def load_or_start_session():
        # All-synchronous: SQLAlchemy's Session and everything run_turn()
        # touches (DB queries, the Ollama HTTP call) are blocking calls.
        # Doing this inline in the async handler blocks the *entire*
        # event loop for the duration - including other connections'
        # websocket pings, which start timing out under any real
        # concurrency (found via stress-testing). asyncio.to_thread here
        # and around each turn below keeps the event loop free.
        patient = get_or_create_patient(db, phone)
        session = get_active_session(db, ConversationChannel.web_chat, phone)
        if session is None:
            state, greeting = initial_state(patient)
            session = create_session(db, ConversationChannel.web_chat, phone, patient.id, state)
            append_history(session, "assistant", greeting)
            db.commit()
            return session, state, greeting
        return session, session.state, (session.history[-1]["content"] if session.history else None)

    def process_turn(state: dict, user_input: str):
        append_history(session, "user", user_input)
        new_state, reply = run_turn(db, state, user_input, llm=_llm)
        save_state(session, new_state, is_emergency=new_state.get("is_emergency", False))
        append_history(session, "assistant", reply)
        db.commit()
        return new_state, reply

    try:
        session, state, first_message = await asyncio.to_thread(load_or_start_session)
        if first_message:
            await websocket.send_json({"role": "assistant", "content": first_message})

        while True:
            user_input = await websocket.receive_text()
            if not user_input.strip():
                continue

            state, reply = await asyncio.to_thread(process_turn, state, user_input)

            await websocket.send_json({"role": "assistant", "content": reply, "stage": state.get("stage")})

    except WebSocketDisconnect:
        logger.info("Chat websocket disconnected (phone=%s)", phone)
    finally:
        live_connections.unregister(ConversationChannel.web_chat, phone)
        db.close()
