from app.core.logging import redact


def test_email_is_masked():
    out = redact("contact elena.ros@globalcorp.io please")
    assert "elena.ros" not in out
    assert "e***@globalcorp.io" in out


def test_phone_is_masked_to_last_four():
    out = redact("from +91 89819-64505 today")
    assert "89819" not in out
    assert "***4505" in out


def test_dates_and_uuids_are_left_alone():
    assert redact("on 2026-10-26") == "on 2026-10-26"
    uid = "9c1f2a44-5b3e-4f10-8a77-123456789012"
    assert redact(f"job {uid}") == f"job {uid}"


def test_bearer_and_webhook_secret_and_keys_are_removed():
    assert "abc123" not in redact("Authorization: Bearer abc123.def")
    assert "s3cr3t" not in redact("POST /webhooks/wati/s3cr3t HTTP/1.1")
    assert "gsk_" not in redact("key gsk_abcdefghijklmnop")
