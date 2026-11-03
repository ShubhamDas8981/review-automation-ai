"""Spotlighting: mark untrusted text so the LLM can tell data from instructions."""
import re
import secrets


def spotlight(untrusted: str) -> tuple[str, str]:
    """Return (wrapped_text, boundary).

    - a random boundary means an attacker cannot forge the closing tag
    - datamarking replaces whitespace with '^' so injected text is visibly 'data'
    Pass `boundary` to prompts.untrusted_notice() so the model knows the rules.
    """
    boundary = secrets.token_hex(8)
    cleaned = untrusted.replace(boundary, "").replace("^", "")
    marked = re.sub(r"\s+", "^", cleaned.strip())
    return f"<data_{boundary}>{marked}</data_{boundary}>", boundary


def unmark(text: str) -> str:
    """Undo datamarking if the model echoes it back."""
    return text.replace("^", " ")
