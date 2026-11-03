import os
import subprocess
import sys


def _load(env):
    base = {k: v for k, v in os.environ.items()
            if not k.startswith(("WEBHOOK_", "WATCH_", "LEMIN_"))}
    code = ("from app.core.config import settings as s; "
            "print(repr(s.webhook_secret), repr(s.watch_phone))")
    out = subprocess.run([sys.executable, "-c", code], env={**base, **env},
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_new_names():
    assert _load({"GROQ_API_KEY": "x", "WEBHOOK_SECRET": "abc", "WATCH_PHONE": "91"}) == "'abc' '91'"


def test_old_lemin_names_still_work():
    assert _load({"GROQ_API_KEY": "x", "LEMIN_WEBHOOK_SECRET": "old", "LEMIN_WATCH_PHONE": "92"}) == "'old' '92'"
