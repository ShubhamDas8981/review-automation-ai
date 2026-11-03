import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_webhook_secret
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import WEBHOOK_SKIPPED
from app.core.redis import r
from app.services.jobs import enqueue_review
from app.services.wati import extract_messages
from app.utils.phone import digits

log = get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _message_id(m: dict) -> str:
    """Dedupe key. Falls back to a hash so messages without an id never collide."""
    if m["id"]:
        return str(m["id"])
    raw = f"{m['from']}|{m['ts']}|{m['text']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _created_at(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat()


def _handle_payload(payload: dict) -> int:
    """Blocking work (Redis + Celery), run in a threadpool."""
    queued = 0
    for m in extract_messages(payload):
        if settings.watch_phone and digits(m["from"]) != digits(settings.watch_phone):
            WEBHOOK_SKIPPED.labels("not_watched_number").inc()
            log.info("message skipped", extra={"reason": "not watched number"})
            continue

        msg_id = _message_id(m)
        if not r.set(f"seen:{msg_id}", 1, nx=True, ex=settings.seen_ttl):
            WEBHOOK_SKIPPED.labels("duplicate").inc()
            log.info("message skipped", extra={"reason": "duplicate"})
            continue

        enqueue_review(m["text"], _created_at(m["ts"]), phone=m["from"], source="webhook")
        log.info("webhook message queued", extra={"wamid": msg_id})
        queued += 1
    return queued


# Wati calls this whenever a WhatsApp message arrives
@router.post("/wati/{secret}", dependencies=[Depends(require_webhook_secret)])
async def wati_webhook(request: Request):
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # log shape, never content
    log.debug("webhook received", extra={"type": payload.get("type")})

    await run_in_threadpool(_handle_payload, payload)
    return {"ok": True}  # always 200 quickly so Wati doesn't retry
