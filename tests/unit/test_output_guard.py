import pytest

from app.guardrails.output_guard import check_reply, check_ticket
from app.guardrails.validators import find_unauthorized_promise


@pytest.mark.parametrize("text", [
    "We've refunded your order.",
    "We have processed your refund.",
    "Your refund has been issued.",
])
def test_promises_detected(text):
    assert find_unauthorized_promise(text)


def test_reply_with_false_promise_is_rejected():
    result = check_reply("Thanks! We've refunded your order.")
    assert not result.passed


def test_normal_reply_passes():
    assert check_reply("Thank you for your kind words! We hope to see you again.").passed


def test_too_long_reply_rejected():
    assert not check_reply("One. Two. Three. Four. Five. Six.").passed


def test_ticket_with_invented_email_rejected():
    ticket = {"name": None, "email": "made.up@x.com", "issue": "charged twice"}
    assert not check_ticket(ticket, "I was charged twice").passed


def test_ticket_with_real_email_passes():
    ticket = {"name": "Elena", "email": "elena@x.com", "issue": "charged twice"}
    assert check_ticket(ticket, "I'm Elena, elena@x.com, charged twice").passed
