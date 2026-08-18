"""Deterministic keyword match for "I'd like my report" style messages —
same rationale as app/services/emergency.py: this gates whether we
re-offer a report the patient previously declined, and a keyword check is
simpler and more predictable than asking the local LLM to classify intent
for something this narrow.
"""

_REPORT_REQUEST_PHRASES = [
    "my report",
    "send my report",
    "get my report",
    "report ready",
    "want my report",
    "visit report",
    "can i get the report",
    "can i have my report",
]


def mentions_report_request(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _REPORT_REQUEST_PHRASES)
