import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.workers.celery_app import celery_app

client = TestClient(app)

PAYLOAD = {
    "eventType": "message",
    "whatsappMessageId": "wamid.ABC",
    "waId": "918981964505",
    "text": "I was charged twice",
    "type": "text",
    "timestamp": "1700000000",
    "owner": False,
}


@pytest.fixture
def sent_tasks(monkeypatch):
    calls = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, args=None, **kw: calls.append((name, args)))
    return calls


def test_webhook_queues_job_and_dedupes(sent_tasks):
    url = "/webhooks/wati/test-secret"

    assert client.post(url, json=PAYLOAD).status_code == 200
    assert client.post(url, json=PAYLOAD).status_code == 200   # duplicate delivery

    assert len(sent_tasks) == 1                                 # queued only once
    name, args = sent_tasks[0]
    assert name == "tasks.process_review"
    assert args[0]["review"] == "I was charged twice"
    assert args[0]["phone"] == "918981964505"

    latest = client.get("/review/latest").json()
    assert latest["status"] == "queued"


def test_messages_without_id_do_not_collide(sent_tasks):
    url = "/webhooks/wati/test-secret"
    base = {"eventType": "message", "waId": "1", "type": "text", "owner": False}
    a = {**base, "timestamp": "1", "text": "first"}
    b = {**base, "timestamp": "2", "text": "second"}
    client.post(url, json=a)
    client.post(url, json=b)
    assert len(sent_tasks) == 2


def test_watch_phone_filter(sent_tasks, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "watch_phone", "+91 99999 00000")
    client.post("/webhooks/wati/test-secret", json=PAYLOAD)
    assert sent_tasks == []


def test_invalid_json_is_400():
    resp = client.post("/webhooks/wati/test-secret", content=b"not json",
                       headers={"content-type": "application/json"})
    assert resp.status_code == 400


def test_manual_endpoint_and_job_lookup(sent_tasks):
    resp = client.post("/review/", json={"review": "Great!"})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    assert client.get(f"/review/{job_id}").json()["status"] == "queued"
    assert client.get("/review/does-not-exist").status_code == 404


def test_health_and_metrics():
    assert client.get("/health").json() == {"status": "ok"}
    body = client.get("/metrics").text
    assert "http_requests_total" in body
    assert "test-secret" not in body        # secret must never reach Prometheus labels


def test_our_own_replies_do_not_create_jobs(sent_tasks):
    echo = {**PAYLOAD, "eventType": "sessionMessageSent", "owner": True}
    assert client.post("/webhooks/wati/test-secret", json=echo).status_code == 200
    assert sent_tasks == []
