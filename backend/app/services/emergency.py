"""Emergency-language detection.

Deliberately deterministic (keyword match), not LLM-based: this gates a
safety-critical fast-path, and a local 7B model's occasional miss is not
an acceptable failure mode here. False positives (routing a non-emergency
to the human-alert path) are the safe failure direction; false negatives
are not, so keep this list broad rather than clever.
"""

_EMERGENCY_PHRASES = [
    "chest pain",
    "can't breathe",
    "cannot breathe",
    "can't breath",
    "difficulty breathing",
    "not breathing",
    "unconscious",
    "unresponsive",
    "severe bleeding",
    "heavy bleeding",
    "bleeding a lot",
    "suicide",
    "kill myself",
    "want to die",
    "overdose",
    "stroke",
    "slurred speech",
    "numbness on one side",
    "face drooping",
    "seizure",
    "heart attack",
    "choking",
    "severe allergic reaction",
    "anaphylaxis",
    "can't wake up",
    "cannot wake up",
    "poisoned",
    "poisoning",
]


def detect_emergency(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _EMERGENCY_PHRASES)
