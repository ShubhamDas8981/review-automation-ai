from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_wrong_secret_is_forbidden():
    resp = client.post("/webhooks/wati/wrong-secret", json={})
    assert resp.status_code == 403


def test_request_id_header_is_returned():
    resp = client.post("/webhooks/wati/wrong-secret", json={})
    assert resp.headers.get("x-request-id")
