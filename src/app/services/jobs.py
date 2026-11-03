import json
import uuid

import redis

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import REVIEWS_RECEIVED
from app.core.redis import r
from app.workers.celery_app import celery_app

log = get_logger(__name__)


def set_job(job_id: str, data: dict) -> None:
    r.set(f"job:{job_id}", json.dumps(data), ex=settings.result_ttl)


def get_job(job_id: str) -> dict | None:
    raw = r.get(f"job:{job_id}")
    return json.loads(raw) if raw else None


def get_latest_job_id() -> str | None:
    return r.get("latest_job_id")


def update_job(job_id: str, **fields) -> None:
    """Merge fields into the job. Optimistic locking: parallel sub-tasks
    (HubSpot + WhatsApp) update the same key, so retry if it changed under us."""
    key = f"job:{job_id}"
    with r.pipeline() as pipe:
        for _ in range(5):
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                data = json.loads(raw) if raw else {}
                data.update(fields)
                pipe.multi()
                pipe.set(key, json.dumps(data), ex=settings.result_ttl)
                pipe.execute()
                return
            except redis.WatchError:
                continue
    # contention never cleared: fall back to a plain merge write
    data = get_job(job_id) or {}
    data.update(fields)
    set_job(job_id, data)


def enqueue_review(
    review_text: str,
    created_at: str,
    phone: str | None = None,
    source: str = "manual",
) -> str:
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "review": review_text,
        "created_at": created_at,
        "phone": phone,
    }
    set_job(job_id, {"status": "queued"})
    r.set("latest_job_id", job_id)
    celery_app.send_task("tasks.process_review", args=[job])

    REVIEWS_RECEIVED.labels(source).inc()
    log.info("job enqueued", extra={"source": source})
    return job_id
