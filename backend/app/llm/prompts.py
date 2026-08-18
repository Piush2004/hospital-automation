"""Prompt templates, one function per agent that needs the LLM."""


def build_triage_messages(symptom_text: str, department_names: list[str]) -> list[dict]:
    dept_list = "\n".join(f"- {name}" for name in department_names)
    system = (
        "You are a hospital triage assistant. Given a patient's description of "
        "their symptoms, pick the single most appropriate department from this "
        "exact list:\n"
        f"{dept_list}\n\n"
        "Respond with ONLY a JSON object, no other text, in this exact shape:\n"
        '{"department": "<one of the department names above, verbatim>", '
        '"reasoning": "<one short sentence>"}\n'
        "If nothing fits well, use \"General Medicine\"."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": symptom_text},
    ]
