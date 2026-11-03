import httpx

from app.core.config import settings
from app.core.exceptions import HubSpotError
from app.core.metrics import EXTERNAL_DURATION, EXTERNAL_REQUESTS, timed


def hs_request(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        with timed(EXTERNAL_DURATION, service="hubspot"):
            resp = httpx.request(
                method,
                f"{settings.hubspot_api}{path}",
                headers={"Authorization": f"Bearer {settings.hubspot_token}"},
                timeout=20,
                **kwargs,
            )
    except httpx.RequestError as e:
        EXTERNAL_REQUESTS.labels("hubspot", "network_error").inc()
        raise HubSpotError(f"Network error: {type(e).__name__}", retryable=True) from e

    if resp.status_code == 429 or resp.status_code >= 500:
        EXTERNAL_REQUESTS.labels("hubspot", "retryable_error").inc()
        raise HubSpotError(f"HubSpot {resp.status_code}: {resp.text[:300]}", retryable=True)
    if resp.status_code >= 400:
        EXTERNAL_REQUESTS.labels("hubspot", "client_error").inc()
        raise HubSpotError(f"HubSpot {resp.status_code}: {resp.text[:300]}", retryable=False)

    EXTERNAL_REQUESTS.labels("hubspot", "ok").inc()
    return resp


def find_or_create_contact(email: str, name: str | None, phone: str | None) -> str:
    resp = hs_request(
        "POST",
        "/crm/v3/objects/contacts/search",
        json={
            "filterGroups": [
                {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
            ],
            "limit": 1,
        },
    )
    results = resp.json().get("results", [])
    if results:
        return results[0]["id"]

    props = {"email": email}
    if name:
        first, _, last = name.partition(" ")
        props["firstname"] = first
        if last:
            props["lastname"] = last
    if phone:
        props["phone"] = phone

    resp = hs_request("POST", "/crm/v3/objects/contacts", json={"properties": props})
    return resp.json()["id"]


def build_ticket_properties(review: str, ticket: dict, phone: str | None) -> dict:
    name, email = ticket.get("name"), ticket.get("email")
    issue = ticket.get("issue") or review[:100]

    content = (
        f"Customer review (via WhatsApp):\n{review}\n\n"
        f"Name: {name or '-'}\nEmail: {email or '-'}\nPhone: {phone or '-'}\n"
        f"Extracted issue: {issue}"
    )
    return {
        "subject": f"Negative review: {issue}"[:200],
        "content": content,
        "hs_pipeline": settings.hubspot_pipeline,
        "hs_pipeline_stage": settings.hubspot_stage,
        "hs_ticket_priority": settings.hubspot_priority,
    }


def create_ticket(properties: dict) -> str:
    resp = hs_request("POST", "/crm/v3/objects/tickets", json={"properties": properties})
    return resp.json()["id"]


def associate_ticket_with_contact(ticket_id: str, contact_id: str) -> None:
    hs_request(
        "PUT",
        f"/crm/v4/objects/tickets/{ticket_id}/associations/default/contacts/{contact_id}",
    )


def ticket_url(ticket_id: str) -> str:
    return (
        f"https://{settings.hubspot_app_host}/contacts/"
        f"{settings.hubspot_portal_id}/record/0-5/{ticket_id}"
    )
