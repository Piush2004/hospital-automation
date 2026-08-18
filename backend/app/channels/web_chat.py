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

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.agents.orchestrator import initial_state, run_turn
from app.db import SessionLocal
from app.llm.ollama_client import OllamaClient
from app.models import ConversationChannel
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
    db = SessionLocal()

    try:
        patient = get_or_create_patient(db, phone)
        session = get_active_session(db, ConversationChannel.web_chat, phone)

        if session is None:
            state, greeting = initial_state(patient)
            session = create_session(db, ConversationChannel.web_chat, phone, patient.id, state)
            append_history(session, "assistant", greeting)
            db.commit()
            await websocket.send_json({"role": "assistant", "content": greeting})
        else:
            state = session.state
            if session.history:
                await websocket.send_json({"role": "assistant", "content": session.history[-1]["content"]})

        while True:
            user_input = await websocket.receive_text()
            if not user_input.strip():
                continue

            append_history(session, "user", user_input)

            new_state, reply = run_turn(db, state, user_input, llm=_llm)
            state = new_state
            save_state(session, state, is_emergency=state.get("is_emergency", False))
            append_history(session, "assistant", reply)
            db.commit()

            await websocket.send_json({"role": "assistant", "content": reply, "stage": state.get("stage")})

    except WebSocketDisconnect:
        logger.info("Chat websocket disconnected (phone=%s)", phone)
    finally:
        db.close()
