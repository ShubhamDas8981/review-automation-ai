import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import WatiError
from app.services import wati


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = str(self._body)

    def json(self):
        return self._body


@pytest.fixture
def capture(monkeypatch):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json})
        return capture.response

    capture.response = FakeResponse()
    monkeypatch.setattr(wati.httpx, "post", fake_post)
    return calls


def test_request_shape(capture):
    wati.send_text("918981964505", "Thanks!")
    call = capture[0]
    assert call["url"] == "https://live-mt-server.wati.io/api/ext/v3/conversations/messages/text"
    assert call["headers"]["Authorization"] == "Bearer test-token"
    assert call["json"] == {"target": "918981964505", "text": "Thanks!", "is_bot": True}


def test_token_that_already_has_bearer_prefix_is_not_doubled(capture, monkeypatch):
    monkeypatch.setattr(settings, "wati_api_token", "Bearer abc.def")
    wati.send_text("911", "x")
    assert capture[0]["headers"]["Authorization"] == "Bearer abc.def"


def test_channel_number_builds_channel_colon_number_target(capture, monkeypatch):
    monkeypatch.setattr(settings, "wati_channel_number", "123456789")
    wati.send_text("1415552671", "x")
    assert capture[0]["json"]["target"] == "123456789:1415552671"


def test_missing_token_is_not_retryable(monkeypatch):
    monkeypatch.setattr(settings, "wati_api_token", None)
    with pytest.raises(WatiError) as e:
        wati.send_text("911", "x")
    assert e.value.retryable is False


@pytest.mark.parametrize("status,retryable", [(429, True), (500, True), (503, True),
                                              (400, False), (401, False), (403, False)])
def test_error_statuses_and_retryability(monkeypatch, status, retryable):
    monkeypatch.setattr(wati.httpx, "post", lambda *a, **k: FakeResponse(status, {"message": "nope"}))
    with pytest.raises(WatiError) as e:
        wati.send_text("911", "x")
    assert e.value.retryable is retryable


def test_network_error_is_retryable(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(wati.httpx, "post", boom)
    with pytest.raises(WatiError) as e:
        wati.send_text("911", "x")
    assert e.value.retryable is True
