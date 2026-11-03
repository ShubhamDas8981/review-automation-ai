from app.ai.workflow import process_review
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import JOBS_FINISHED, SENTIMENT
from app.schemas.job import JobStatus
from app.services.jobs import set_job, update_job
from app.services.messages import format_ticket_message
from app.utils.phone import digits
from app.workers.celery_app import celery_app
from app.workers.tasks.hubspot import create_hubspot_ticket_task
from app.workers.tasks.messaging import send_message_task

log = get_logger(__name__)


@celery_app.task(name="tasks.process_review", bind=True, max_retries=2)
def process_review_task(self, job: dict):
    job_id = job["job_id"]
    set_job(job_id, {"status": JobStatus.PROCESSING})

    # ---- 1. run guards + LLM workflow ----
    try:
        result = process_review(job["review"])
    except Exception as e:
        log.warning(
            "workflow failed", exc_info=True, extra={"attempt": self.request.retries + 1}
        )
        if self.request.retries < self.max_retries:
            update_job(job_id, status=JobStatus.RETRYING, error=type(e).__name__)
            raise self.retry(exc=e, countdown=5 * (2 ** self.request.retries))
        set_job(job_id, {"status": JobStatus.FAILED, "error": type(e).__name__})
        JOBS_FINISHED.labels("failed").inc()
        return

    # ---- 2. guardrail outcomes (never retried: same input gives the same verdict) ----
    if result["blocked"]:
        if result["block_stage"] == "input":
            status = JobStatus.BLOCKED
            set_job(job_id, {
                "status": status,
                "reason": result["block_reason"],
                "created_at": job["created_at"],
            })
        else:
            status = JobStatus.NEEDS_REVIEW
            set_job(job_id, {
                "status": status,
                "reason": result["block_reason"],
                "review": job["review"],
                "sentiment": result["sentiment"],
                "created_at": job["created_at"],
            })
        JOBS_FINISHED.labels(status.value).inc()
        log.warning("job held by guardrails", extra={"reason": result["block_reason"]})
        return

    # ---- 3. success path ----
    sentiment = result["sentiment"]
    SENTIMENT.labels(sentiment).inc()

    payload = {
        "status": JobStatus.DONE,
        "review": job["review"],
        "created_at": job["created_at"],
        "sentiment": sentiment,
    }
    phone = digits(job.get("phone") or settings.watch_phone)

    if sentiment == "negative":
        ticket = result["ticket_json"]
        payload["ticket_json"] = ticket
        payload["hubspot_ticket"] = "pending"
        payload["ticket_copy_status"] = "pending" if phone else "skipped: no phone number"
        set_job(job_id, payload)   # write first; the sub-tasks merge into it

        create_hubspot_ticket_task.delay(job_id, job["review"], ticket, phone)
        if phone:
            send_message_task.delay(
                job_id, phone, format_ticket_message(ticket), "ticket_copy_status"
            )
    else:
        payload["reply"] = result["reply"]
        if phone and result["reply"]:
            payload["reply_status"] = "pending"
            set_job(job_id, payload)
            send_message_task.delay(job_id, phone, result["reply"], "reply_status")
        else:
            payload["reply_status"] = "skipped: no phone number"
            set_job(job_id, payload)

    JOBS_FINISHED.labels("done").inc()
    log.info("job done", extra={"sentiment": sentiment})
