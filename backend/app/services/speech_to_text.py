"""Local speech-to-text via faster-whisper.

The model loads once per process (a few seconds) and is reused for every
transcription — same singleton pattern as OllamaClient in web_chat.py.
Accepts raw audio bytes in whatever format the browser's MediaRecorder
produced (webm/opus by default): faster-whisper decodes via ffmpeg (the
`av` package, one of its own dependencies) internally, so no
client-side conversion is needed.
"""

import io
import logging

from faster_whisper import WhisperModel

from app.config import get_settings

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        settings = get_settings()
        logger.info(
            "Loading faster-whisper model %r (device=%s, compute_type=%s)...",
            settings.stt_model_size,
            settings.stt_device,
            settings.stt_compute_type,
        )
        _model = WhisperModel(
            settings.stt_model_size, device=settings.stt_device, compute_type=settings.stt_compute_type
        )
    return _model


def transcribe(audio_bytes: bytes, language: str = "en") -> str:
    """Transcribes one audio clip. Returns "" for silence/no speech
    detected rather than raising — a voice UI should treat "nothing
    heard" as a normal, expected outcome, not an error.
    """
    if not audio_bytes:
        return ""

    model = _get_model()
    segments, _info = model.transcribe(io.BytesIO(audio_bytes), language=language, vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()
