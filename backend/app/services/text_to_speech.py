"""Local text-to-speech via Piper.

The voice model loads once per process, same singleton pattern as
speech_to_text.py. Output is a plain WAV clip — universally playable by
browsers via <audio> or Web Audio API with zero client-side decoding
beyond what every browser already supports natively, so no reason to
reach for a compressed format here.
"""

import io
import logging
import wave

from piper import PiperVoice

from app.config import get_settings

logger = logging.getLogger(__name__)

_voice: PiperVoice | None = None


def _get_voice() -> PiperVoice:
    global _voice
    if _voice is None:
        settings = get_settings()
        model_path = settings.voices_dir / f"{settings.tts_voice}.onnx"
        if not model_path.exists():
            raise FileNotFoundError(
                f"Piper voice model not found at {model_path}. Download it with:\n"
                f"  python -m piper.download_voices --download-dir storage/voices {settings.tts_voice}"
            )
        logger.info("Loading Piper voice %r...", settings.tts_voice)
        _voice = PiperVoice.load(str(model_path))
    return _voice


def synthesize(text: str) -> bytes:
    """Synthesizes `text` to a WAV audio clip. Returns b"" for empty text
    rather than raising or producing silence."""
    if not text.strip():
        return b""

    voice = _get_voice()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    return buffer.getvalue()
