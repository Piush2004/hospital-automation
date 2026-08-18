"""In-memory registry of live channel connections, keyed by (channel, external_id).

Single-process, local-prototype scope: lets an out-of-band event (a mock
payment completing, a doctor finishing a visit) push a message into an
already-open chat session instead of the patient only finding it on
their next reconnect. Not meant to survive process restarts or scale
beyond one backend instance — that's fine for this MVP; a real deployment
would use a proper pub/sub layer here.

Only meaningful within the FastAPI process itself (e.g. web_chat.py's
websocket handler). CLI tools like doctor_cli.py run as separate
processes and never see anything registered here — they rely purely on
DB persistence (see app/services/notifications.py).
"""

from typing import Protocol

from app.models import ConversationChannel


class SendsJSON(Protocol):
    async def send_json(self, data: dict) -> None: ...


_connections: dict[tuple[str, str], SendsJSON] = {}


def register(channel: ConversationChannel, external_id: str, connection: SendsJSON) -> None:
    _connections[(channel.value, external_id)] = connection


def unregister(channel: ConversationChannel, external_id: str) -> None:
    _connections.pop((channel.value, external_id), None)


def get(channel: ConversationChannel, external_id: str) -> SendsJSON | None:
    return _connections.get((channel.value, external_id))
