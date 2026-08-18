"""Outbound side of the WhatsApp channel: ask the gateway (whatsapp-gateway/,
a separate Node process) to relay a message over its already-open Baileys
socket. Used for proactive pushes (payment confirmed, report ready) - the
inbound/reply flow doesn't need this, since the gateway gets the reply
synchronously in the webhook HTTP response (see
app/channels/whatsapp_webhook.py).
"""

import httpx

from app.config import get_settings


def send_whatsapp_message(phone: str, text: str) -> None:
    settings = get_settings()
    resp = httpx.post(
        f"{settings.whatsapp_gateway_url.rstrip('/')}/send",
        json={"phone": phone, "message": text},
        timeout=10.0,
    )
    resp.raise_for_status()
