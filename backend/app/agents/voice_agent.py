"""Voice agent: composes speech-to-text, the same orchestrator every
channel uses, and text-to-speech into one "process one voice turn"
function. app/channels/voice_ws.py is the thin websocket adapter over
this — the same "channels are thin, agents do the real work" pattern as
every other channel in this codebase.

Browser-based mic/speaker widget, not real telephony — see CLAUDE.md and
README for that caveat. Not LLM-based itself (the composition logic is
plain glue); the LLM is used inside run_turn() exactly as it is for
every other channel, only for triage classification.
"""

from sqlalchemy.orm import Session

from app.agents.orchestrator import ConversationState, run_turn
from app.llm.ollama_client import OllamaClient
from app.services.speech_to_text import transcribe
from app.services.text_to_speech import synthesize

_NO_SPEECH_REPLY = "Sorry, I didn't catch that - could you say it again?"


def process_voice_turn(
    db: Session,
    state: ConversationState,
    audio_bytes: bytes,
    llm: OllamaClient | None = None,
) -> tuple[ConversationState, str, str, bytes]:
    """Returns (new_state, transcribed_text, reply_text, reply_audio_wav).

    `transcribed_text` is returned separately rather than folded silently
    into the turn, so the channel can show the patient what was actually
    heard — important for voice specifically: STT errors are common, and
    a patient silently misunderstood is worse here than in a text channel
    where they can see exactly what they typed.
    """
    transcribed_text = transcribe(audio_bytes)

    if not transcribed_text:
        return state, "", _NO_SPEECH_REPLY, synthesize(_NO_SPEECH_REPLY)

    new_state, reply_text = run_turn(db, state, transcribed_text, llm=llm)
    reply_audio = synthesize(reply_text)
    return new_state, transcribed_text, reply_text, reply_audio
