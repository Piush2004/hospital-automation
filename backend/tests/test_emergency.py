import pytest

from app.services.emergency import detect_emergency


@pytest.mark.parametrize(
    "text",
    [
        "I have severe chest pain",
        "She is unconscious and not breathing",
        "I think I want to kill myself",
        "He took an overdose an hour ago",
    ],
)
def test_detects_emergency_phrases(text):
    assert detect_emergency(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "I have a mild headache",
        "Can I book a checkup next week?",
        "My skin has been a bit itchy lately",
    ],
)
def test_does_not_flag_routine_text(text):
    assert detect_emergency(text) is False
