"""Wati (WhatsApp): parse inbound webhooks, send outbound session text.

Send API (v3): POST {base}/api/ext/v3/conversations/messages/text
  body: {"target": "<number or channel:number>", "text": "...", "is_bot": true}
HTTP 200 means Wati ACCEPTED the message, not that it was delivered.
"""
import httpx

from app.core.config import settings
from app.core.exceptions import WatiError
from app.core.metrics import EXTERNAL_DURATION, EXTERNAL_REQUESTS, timed

# Events that mean "a customer sent us something". Wati also posts events for messages
# WE send (sessionMessageSent, delivered, read...), which must never be processed.
_INBOUND_EVENTS = {"message", "messagereceived", "newcontactmessagereceived", "message_bsuid"}


def _get(payload: dict, *keys: str):
    """First non-empty value among several key spellings (camelCase / snake_case)."""
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def extract_messages(payload: dict) -> list[dict]:
    """Return inbound customer text messages from a Wati webhook payload."""
    event = str(_get(payload, "eventType", "event_type") or "").lower()
    if event not in _INBOUND_EVENTS:
        return []
    if _get(payload, "owner") is True:      # sent by the business or an operator
        return []
    if str(_get(payload, "type") or "").lower() != "text":
        return []

    text = _get(payload, "text")
    if not isinstance(text, str) or not text.strip():
        return []

    return [{
        "id": _get(payload, "whatsappMessageId", "whatsapp_message_id", "id"),
        "from": _get(payload, "waId", "wa_id"),
        "text": text,
        "ts": _get(payload, "timestamp"),
    }]


def _error_text(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            return str(data.get("message") or data.get("details") or "")[:200]
    except ValueError:
        pass
    return resp.text[:200]


def send_text(to: str, text: str) -> None:
    """Send a WhatsApp text inside an open session. Raises WatiError(retryable=...)."""
    token = settings.wati_api_token
    if not token:
        raise WatiError("WATI_API_TOKEN not set", retryable=False)

    auth = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    # With several connected numbers, target is "<your channel number>:<customer number>".
    target = f"{settings.wati_channel_number}:{to}" if settings.wati_channel_number else to
    url = f"{settings.wati_api_base_url.rstrip('/')}/api/ext/v3/conversations/messages/text"

    try:
        with timed(EXTERNAL_DURATION, service="wati"):
            resp = httpx.post(
                url,
                headers={"Authorization": auth, "Accept": "application/json"},
                json={"target": target, "text": text, "is_bot": True},
                timeout=20,
            )
    except httpx.RequestError as e:
        EXTERNAL_REQUESTS.labels("wati", "network_error").inc()
        raise WatiError(f"Network error: {type(e).__name__}", retryable=True) from e

    if resp.status_code == 429 or resp.status_code >= 500:
        EXTERNAL_REQUESTS.labels("wati", "retryable_error").inc()
        raise WatiError(f"Wati {resp.status_code}", retryable=True)
    if resp.status_code >= 400:
        EXTERNAL_REQUESTS.labels("wati", "client_error").inc()
        raise WatiError(f"Wati {resp.status_code}: {_error_text(resp)}", retryable=False)

    EXTERNAL_REQUESTS.labels("wati", "ok").inc()
