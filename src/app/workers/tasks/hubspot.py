import json

from app.core.config import settings
from app.core.exceptions import HubSpotError
from app.core.logging import get_logger
from app.core.redis import r
from app.services import hubspot
from app.services.jobs import update_job
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="tasks.create_hubspot_ticket", bind=True, max_retries=5)
def create_hubspot_ticket_task(self, job_id: str, review: str, ticket: dict, phone: str):
    # a retried or redelivered task must not create a second ticket
    existing = r.get(f"hubspot:{job_id}")
    if existing:
        update_job(job_id, hubspot_ticket=json.loads(existing))
        return

    if not settings.hubspot_token:
        update_job(job_id, hubspot_ticket="failed: HUBSPOT_TOKEN not set")
        return

    properties = hubspot.build_ticket_properties(review, ticket, phone)

    try:
        ticket_id = hubspot.create_ticket(properties)
    except HubSpotError as e:
        if e.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=10 * (2 ** self.request.retries))
        update_job(job_id, hubspot_ticket=f"failed: {e}")
        return

    info = {"id": ticket_id, "url": hubspot.ticket_url(ticket_id)}
    # remember it before anything else can fail, so a retry never duplicates the ticket
    r.set(f"hubspot:{job_id}", json.dumps(info), ex=settings.ticket_ttl)

    # best effort: link the ticket to the customer's contact (needs an email)
    email = ticket.get("email")
    if email:
        try:
            contact_id = hubspot.find_or_create_contact(email, ticket.get("name"), phone)
            hubspot.associate_ticket_with_contact(ticket_id, contact_id)
            info["contact_id"] = contact_id
        except HubSpotError as e:
            info["contact_error"] = str(e)
            log.warning("hubspot contact link failed")

    update_job(job_id, hubspot_ticket=info)
    log.info("hubspot ticket created", extra={"ticket_id": ticket_id})
