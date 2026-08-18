from app.agents.triage_agent import classify_department
from app.llm.ollama_client import OllamaUnavailableError
from app.models import Department


class _StubLLM:
    def __init__(self, result=None, raise_unavailable=False):
        self._result = result
        self._raise_unavailable = raise_unavailable

    def chat_json(self, messages, temperature=0.1, retries=2):
        if self._raise_unavailable:
            raise OllamaUnavailableError("stub: no model reachable")
        return self._result


def _seed_departments(db):
    for name in ["General Medicine", "Cardiology", "Dermatology", "Pediatrics", "Orthopedics", "ENT"]:
        db.add(Department(name=name))
    db.flush()


def test_uses_llm_result_when_valid(db):
    _seed_departments(db)
    llm = _StubLLM(result={"department": "Dermatology", "reasoning": "skin symptoms"})

    department = classify_department(db, "I have a rash on my arm", llm=llm)

    assert department.name == "Dermatology"


def test_falls_back_to_keywords_when_llm_unavailable(db):
    _seed_departments(db)
    llm = _StubLLM(raise_unavailable=True)

    department = classify_department(db, "my child has an ear infection", llm=llm)

    # "child" keyword maps to Pediatrics in the fallback table.
    assert department.name == "Pediatrics"


def test_falls_back_when_llm_returns_unknown_department(db):
    _seed_departments(db)
    llm = _StubLLM(result={"department": "Not A Real Department"})

    department = classify_department(db, "my joint hurts after a fall", llm=llm)

    assert department.name == "Orthopedics"


def test_defaults_to_general_medicine_when_nothing_matches(db):
    _seed_departments(db)
    llm = _StubLLM(raise_unavailable=True)

    department = classify_department(db, "I feel generally unwell", llm=llm)

    assert department.name == "General Medicine"
