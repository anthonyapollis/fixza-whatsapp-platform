"""WhatsApp Cloud API client + webhook signature verification.

In DRY_RUN mode (no WHATSAPP_TOKEN configured) outbound messages are printed
to the log instead of sent, so the whole flow works locally without Meta setup.
"""
from __future__ import annotations

import hashlib
import hmac
import logging

import httpx

from . import config

log = logging.getLogger("fixza.whatsapp")


def verify_signature(payload: bytes, signature_header: str | None) -> bool:
    """Validate X-Hub-Signature-256 (sha256 HMAC of raw body with app secret)."""
    if not config.META_APP_SECRET:
        # No secret configured (local dev) — accept but warn.
        log.warning("META_APP_SECRET not set; skipping webhook signature check")
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        config.META_APP_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


async def send_text(to_wa_id: str, body: str) -> None:
    if config.DRY_RUN:
        # ascii() keeps Windows cp1252 consoles happy with emoji in messages
        log.info("[DRY-RUN] -> %s:\n%s", to_wa_id, ascii(body))
        return
    url = f"{config.GRAPH_API_BASE}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": body},
    }
    headers = {"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            log.error("WhatsApp send failed %s: %s", resp.status_code, resp.text)


def extract_messages(webhook_body: dict) -> list[dict]:
    """Flatten Meta's nested webhook payload into simple message dicts.

    Returns items like:
      {"wa_id": "...", "name": "...", "type": "text", "text": "..."}
      {"wa_id": "...", "name": "...", "type": "location", "lat": .., "lng": ..}
    """
    out: list[dict] = []
    for entry in webhook_body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = {
                c.get("wa_id"): c.get("profile", {}).get("name", "")
                for c in value.get("contacts", [])
            }
            for msg in value.get("messages", []):
                wa_id = msg.get("from", "")
                item = {"wa_id": wa_id, "name": contacts.get(wa_id, "")}
                mtype = msg.get("type")
                if mtype == "text":
                    item.update(type="text", text=msg.get("text", {}).get("body", ""))
                elif mtype == "location":
                    loc = msg.get("location", {})
                    item.update(
                        type="location",
                        lat=loc.get("latitude"),
                        lng=loc.get("longitude"),
                    )
                elif mtype == "interactive":
                    inter = msg.get("interactive", {})
                    reply = inter.get("button_reply") or inter.get("list_reply") or {}
                    item.update(type="text", text=reply.get("id", ""))
                else:
                    item.update(type="unsupported", text="")
                out.append(item)
    return out
