from app.core.config import settings
from app.core.exceptions import WatiError
from app.core.logging import get_logger
from app.core.redis import r
from app.services import wati
from app.services.jobs import update_job
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="tasks.send_message", bind=True, max_retries=4)
def send_message_task(self, job_id: str, to: str, text: str, status_field: str):
    sent_key = f"sent:{job_id}:{status_field}"
    if r.get(sent_key):
        return  # already sent (redelivery)

    try:
        wati.send_text(to, text)
    except WatiError as e:
        if e.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=5 * (2 ** self.request.retries))
        update_job(job_id, **{status_field: f"failed: {e}"})
        log.error("whatsapp send failed", extra={"field": status_field})
        return

    r.set(sent_key, 1, ex=settings.sent_ttl)
    update_job(job_id, **{status_field: "sent", "sent_to": to})
    log.info("whatsapp sent", extra={"field": status_field})
