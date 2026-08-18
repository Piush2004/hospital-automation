"""Triage & Doctor-Assignment agent.

Classifies free-text symptoms into a department, then hands off to the
scheduling agent to pick a doctor. Uses the local LLM for classification
with a deterministic keyword-based fallback — see module docstring in
app/llm/ollama_client.py for why that fallback exists.
"""

import logging

from sqlalchemy.orm import Session

from app.llm.ollama_client import OllamaClient, OllamaUnavailableError
from app.llm.prompts import build_triage_messages
from app.models import Department
from app.services.departments import get_department_by_name, list_departments

logger = logging.getLogger(__name__)

_KEYWORD_MAP: list[tuple[tuple[str, ...], str]] = [
    (("skin", "rash", "acne", "itch", "mole", "eczema"), "Dermatology"),
    (("heart", "palpitation", "blood pressure", "cardiac"), "Cardiology"),
    (("child", "kid", "baby", "infant", "toddler"), "Pediatrics"),
    (("bone", "fracture", "joint", "sprain", "back pain", "knee", "shoulder"), "Orthopedics"),
    (("ear", "nose", "throat", "sinus", "hearing", "tonsil"), "ENT"),
]


def _keyword_fallback(symptom_text: str) -> str:
    lowered = symptom_text.lower()
    for keywords, department in _KEYWORD_MAP:
        if any(kw in lowered for kw in keywords):
            return department
    return "General Medicine"


def classify_department(db: Session, symptom_text: str, llm: OllamaClient | None = None) -> Department:
    """Returns a real Department row, guaranteed to exist (falls back to
    'General Medicine' if the LLM's pick doesn't match a known department).
    """
    departments = list_departments(db)
    department_names = [d.name for d in departments]
    llm = llm or OllamaClient()

    chosen_name: str | None = None
    try:
        result = llm.chat_json(build_triage_messages(symptom_text, department_names))
        if result and isinstance(result.get("department"), str):
            chosen_name = result["department"]
            logger.info("LLM triage: %r -> %r (%s)", symptom_text, chosen_name, result.get("reasoning"))
    except OllamaUnavailableError as exc:
        logger.warning("Ollama unavailable for triage, using keyword fallback: %s", exc)

    department = get_department_by_name(db, chosen_name) if chosen_name else None
    if department is None:
        fallback_name = _keyword_fallback(symptom_text)
        department = get_department_by_name(db, fallback_name)
        logger.info("Triage fallback used: %r -> %r", symptom_text, fallback_name)

    if department is None:
        # Last resort: General Medicine must exist per seed data, but guard anyway.
        department = departments[0]

    return department
