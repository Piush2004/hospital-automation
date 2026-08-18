"""Thin wrapper around the local Ollama HTTP API.

Local models (7B-class, q4 quantized) are noticeably less reliable at
structured JSON / tool-calling output than hosted frontier models. This
client keeps retry + fallback-model logic in one place so every agent
gets the same resilience without duplicating it. Callers that need
structured output should still validate the parsed result themselves and
be ready to fall back to a deterministic path — see
app/agents/triage_agent.py for the pattern.
"""

import json
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class OllamaUnavailableError(RuntimeError):
    """Raised when neither the primary nor fallback model could be reached."""


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.fallback_model = fallback_model or settings.ollama_fallback_model
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def _chat_once(self, model: str, messages: list[dict], json_mode: bool, temperature: float) -> str:
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]

    def chat(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float = 0.2,
        retries: int = 2,
    ) -> str:
        """Send a chat request, retrying the primary model, then trying the
        fallback model once, before giving up.
        """
        last_error: Exception | None = None

        for attempt in range(retries):
            try:
                return self._chat_once(self.model, messages, json_mode, temperature)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last_error = exc
                logger.warning("Ollama primary model %r attempt %d failed: %s", self.model, attempt + 1, exc)

        if self.fallback_model and self.fallback_model != self.model:
            try:
                return self._chat_once(self.fallback_model, messages, json_mode, temperature)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last_error = exc
                logger.warning("Ollama fallback model %r failed: %s", self.fallback_model, exc)

        raise OllamaUnavailableError(f"No Ollama model reachable ({self.model} / {self.fallback_model})") from last_error

    def chat_json(self, messages: list[dict], temperature: float = 0.1, retries: int = 2) -> dict | None:
        """Like chat(), but requests JSON mode and parses the result.

        Returns None (rather than raising) on a parse failure so callers can
        fall back to a deterministic path — a malformed JSON blob from a
        small local model is an expected, not exceptional, outcome.
        """
        try:
            raw = self.chat(messages, json_mode=True, temperature=temperature, retries=retries)
        except OllamaUnavailableError:
            raise

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Ollama returned unparseable JSON: %r", raw)
            return None
