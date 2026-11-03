"""Input guard: runs on untrusted WhatsApp text BEFORE any LLM call.

Layer 1 (always on, microseconds): length + heuristic injection patterns.
Layer 2 (optional): Guardrails AI hub validators, loaded lazily on first use.
    guardrails hub install hub://guardrails/detect_jailbreak
    guardrails hub install hub://guardrails/toxic_language
"""
import re
from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.guardrails import disable_telemetry
from app.core.metrics import GUARD_BLOCKS, GUARD_CHECKS, GUARD_DURATION, timed
from app.guardrails.result import GuardResult

log = get_logger(__name__)

_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all)\b"
        r".{0,30}\b(instructions?|prompts?|rules?|context)\b",
        r"\b(reveal|show|print|repeat|leak)\b.{0,30}\b(system|hidden|initial)\b.{0,15}\bprompt\b",
        r"\byou\s+are\s+now\b.{0,40}\b(mode|admin|developer|dan|jailbroken)\b",
        r"(^|\n)\s*(system|assistant)\s*:",
        r"\bdeveloper\s+mode\b|\bjailbreak\b",
    )
]


def heuristic_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS)


@lru_cache(maxsize=1)
def _hub_guard():
    """Build the Guardrails AI guard once. Returns None if validators aren't installed."""
    try:
        from guardrails import Guard, OnFailAction
        from guardrails.hub import DetectJailbreak, ToxicLanguage
    except ImportError:
        log.warning("guardrails hub validators not installed; using heuristic checks only")
        return None
    try:
        guard = Guard(name="input_guard").use_many(
            DetectJailbreak(
                threshold=settings.guard_injection_threshold,
                on_fail=OnFailAction.EXCEPTION,
            ),
            ToxicLanguage(
                threshold=0.8, validation_method="sentence", on_fail=OnFailAction.EXCEPTION
            ),
        )
        return disable_telemetry(guard)
    except Exception:
        log.error("failed to build hub guard; using heuristic checks only", exc_info=True)
        return None


def _reason_from_error(err: Exception) -> str:
    msg = str(err).lower()
    if "toxic" in msg:
        return "toxic"
    if "jailbreak" in msg or "injection" in msg:
        return "injection"
    return "validation_failed"


def _run_checks(text: str) -> GuardResult:
    if len(text) > settings.guard_max_review_chars:
        return GuardResult(False, text, "too_long")
    if heuristic_injection(text):
        return GuardResult(False, text, "injection")

    guard = _hub_guard()
    if guard is not None:
        try:
            guard.validate(text)
        except Exception as e:
            return GuardResult(False, text, _reason_from_error(e))
    return GuardResult(True, text)


def check_input(text: str) -> GuardResult:
    if not settings.guardrails_enabled:
        return GuardResult(True, text)

    with timed(GUARD_DURATION, stage="input"):
        result = _run_checks(text)

    GUARD_CHECKS.labels("input", "pass" if result.passed else "block").inc()
    if not result.passed:
        GUARD_BLOCKS.labels("input", result.reason or "unknown").inc()
        # log the reason, never the text
        log.warning("input rejected", extra={"reason": result.reason})
        if settings.guard_on_fail_input == "flag":
            return GuardResult(True, text, result.reason)
    return result
