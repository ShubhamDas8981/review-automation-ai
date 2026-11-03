import os

# Must be set before any `app` import (Settings() validates on import).
os.environ["GROQ_API_KEY"] = "test-key"
os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ["WATCH_PHONE"] = ""
os.environ["WATI_API_TOKEN"] = "test-token"
os.environ["WATI_CHANNEL_NUMBER"] = ""
os.environ["GUARDRAILS_ENABLED"] = "true"
# remove old names so a developer's .env can never leak into tests
for _k in ("LEMIN_WEBHOOK_SECRET", "LEMIN_WATCH_PHONE"):
    os.environ.pop(_k, None)

import fakeredis  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402

# Tests never touch a real Redis: every redis.Redis.from_url() returns one in-memory fake.
_fake = fakeredis.FakeRedis(decode_responses=True)
redis.Redis.from_url = classmethod(lambda cls, *a, **k: _fake)


@pytest.fixture(autouse=True)
def _clean_redis():
    _fake.flushall()
    yield
