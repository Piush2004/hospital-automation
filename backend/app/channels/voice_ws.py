"""Voice channel: FastAPI WebSocket adapter over voice_agent.py, mirroring
web_chat.py's structure — see that module's docstring for why blocking
work is wrapped in asyncio.to_thread (a real bug found by stress-testing
this session: an async def handler doing blocking DB/LLM work inline
blocks the *entire* event loop, timing out every other connection under
concurrency). Applies identically here, plus this handler also does
blocking STT/TTS work.

Protocol: connect to `/ws/voice?phone=<phone>`. For each turn, the server
sends a JSON text frame — `{"role": "assistant", "content": <text>,
"heard": <str|null>, "stage": <str>, "has_audio": bool}` — immediately
followed by a binary frame containing the raw WAV reply (only when
`has_audio` is true). `heard` is what STT transcribed from the client's
last utterance (null on the very first greeting, which has no prior
utterance) — sent back so the UI can show "you said: ..." next to the
reply. This matters more for voice than text: STT errors are common and
a patient silently misunderstood is worse than one who can see (and
correct for) what was actually heard. Client sends ONE binary WebSocket
frame per utterance containing the complete recorded audio clip
(push-to-talk style — whatever format the browser's MediaRecorder
produced; see speech_to_text.py for why no client-side conversion is
needed).

Audio goes over its own binary frame rather than base64-embedded in the
JSON deliberately: base64 adds ~33% size, and a moderately long spoken
reply (Piper's WAV output is uncompressed 22050Hz PCM — a ~15s reply is
roughly 650KB raw) can push a base64-JSON frame over the default
websocket max frame size (1MB) and get the connection killed with
"message too big." Found by testing this end-to-end with real synthesized
speech, not by inspection — see CLAUDE.md. Run uvicorn with a raised
`--ws-max-size` (see README) as extra headroom on top of the
binary-frame fix, since a long enough reply could still exceed the
default even without base64 overhead.
"""

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.agents.orchestrator import initial_state
from app.agents.voice_agent import process_voice_turn
from app.db import SessionLocal
from app.llm.ollama_client import OllamaClient
from app.models import ConversationChannel
from app.services import live_connections
from app.services.conversations import append_history, create_session, get_active_session, save_state
from app.services.patients import get_or_create_patient
from app.services.text_to_speech import synthesize

logger = logging.getLogger(__name__)
router = APIRouter()

_llm = OllamaClient()


async def _send_turn(
    websocket: WebSocket, content: str, audio: bytes, stage: str | None, heard: str | None = None
) -> None:
    await websocket.send_json(
        {"role": "assistant", "content": content, "heard": heard, "stage": stage, "has_audio": bool(audio)}
    )
    if audio:
        await websocket.send_bytes(audio)


@router.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket, phone: str = Query(...)) -> None:
    await websocket.accept()
    live_connections.register(ConversationChannel.voice, phone, websocket)
    db = SessionLocal()

    def load_or_start_session():
        patient = get_or_create_patient(db, phone)
        session = get_active_session(db, ConversationChannel.voice, phone)
        if session is None:
            state, greeting = initial_state(patient)
            session = create_session(db, ConversationChannel.voice, phone, patient.id, state)
            append_history(session, "assistant", greeting)
            db.commit()
            return session, state, greeting
        return session, session.state, (session.history[-1]["content"] if session.history else None)

    def process_turn(state: dict, audio_bytes: bytes):
        new_state, transcribed, reply_text, reply_audio = process_voice_turn(db, state, audio_bytes, llm=_llm)
        append_history(session, "user", transcribed or "(inaudible)")
        save_state(session, new_state, is_emergency=new_state.get("is_emergency", False))
        append_history(session, "assistant", reply_text)
        db.commit()
        return new_state, transcribed, reply_text, reply_audio

    try:
        session, state, first_message = await asyncio.to_thread(load_or_start_session)
        if first_message:
            audio = await asyncio.to_thread(synthesize, first_message)
            await _send_turn(websocket, first_message, audio, state.get("stage"))

        while True:
            audio_bytes = await websocket.receive_bytes()
            if not audio_bytes:
                continue

            state, transcribed, reply_text, reply_audio = await asyncio.to_thread(process_turn, state, audio_bytes)
            await _send_turn(websocket, reply_text, reply_audio, state.get("stage"), heard=transcribed or None)

    except WebSocketDisconnect:
        logger.info("Voice websocket disconnected (phone=%s)", phone)
    finally:
        live_connections.unregister(ConversationChannel.voice, phone)
        db.close()
