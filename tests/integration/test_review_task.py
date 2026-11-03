import pytest

from app.core.redis import r
from app.services.jobs import get_job, set_job, update_job
from app.workers.tasks import review as review_mod

JOB = {
    "job_id": "job-1",
    "review": "charged twice, elena@x.com",
    "created_at": "2026-10-26T00:00:00+00:00",
    "phone": "+91 89819-64505",
}


def _state(**over):
    base = {
        "review": JOB["review"], "sentiment": "positive", "reply": "Thanks a lot!",
        "ticket_json": None, "blocked": False, "block_stage": None, "block_reason": None,
    }
    base.update(over)
    return base


@pytest.fixture
def fake_subtasks(monkeypatch):
    calls = {"hubspot": [], "message": []}
    monkeypatch.setattr(review_mod.create_hubspot_ticket_task, "delay",
                        lambda *a: calls["hubspot"].append(a))
    monkeypatch.setattr(review_mod.send_message_task, "delay",
                        lambda *a: calls["message"].append(a))
    return calls


def test_positive_review_sends_reply(monkeypatch, fake_subtasks):
    monkeypatch.setattr(review_mod, "process_review", lambda text: _state())
    review_mod.process_review_task.apply(args=[JOB])

    job = get_job("job-1")
    assert job["status"] == "done" and job["reply_status"] == "pending"
    assert fake_subtasks["message"][0][1] == "918981964505"      # phone normalized to digits
    assert fake_subtasks["hubspot"] == []


def test_negative_review_creates_ticket_and_copy(monkeypatch, fake_subtasks):
    ticket = {"name": "Elena", "email": "elena@x.com", "issue": "charged twice"}
    monkeypatch.setattr(review_mod, "process_review",
                        lambda text: _state(sentiment="negative", reply=None, ticket_json=ticket))
    review_mod.process_review_task.apply(args=[JOB])

    job = get_job("job-1")
    assert job["status"] == "done" and job["ticket_json"] == ticket
    assert len(fake_subtasks["hubspot"]) == 1 and len(fake_subtasks["message"]) == 1


def test_input_block_is_recorded_and_not_retried(monkeypatch, fake_subtasks):
    monkeypatch.setattr(review_mod, "process_review", lambda text: _state(
        blocked=True, block_stage="input", block_reason="injection", sentiment="", reply=None))
    review_mod.process_review_task.apply(args=[JOB])

    job = get_job("job-1")
    assert job == {"status": "blocked", "reason": "injection", "created_at": JOB["created_at"]}
    assert "review" not in job                                    # blocked text is not stored
    assert fake_subtasks == {"hubspot": [], "message": []}


def test_output_block_needs_human_review(monkeypatch, fake_subtasks):
    monkeypatch.setattr(review_mod, "process_review", lambda text: _state(
        blocked=True, block_stage="output", block_reason="unauthorized_claim"))
    review_mod.process_review_task.apply(args=[JOB])

    job = get_job("job-1")
    assert job["status"] == "needs_review" and job["reason"] == "unauthorized_claim"
    assert fake_subtasks == {"hubspot": [], "message": []}


def test_update_job_merges_fields():
    set_job("j", {"status": "done"})
    update_job("j", reply_status="sent")
    update_job("j", sent_to="918981964505")
    assert get_job("j") == {"status": "done", "reply_status": "sent", "sent_to": "918981964505"}
    assert r.ttl("job:j") > 0
