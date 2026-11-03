"""Output guard: validates LLM results BEFORE anything is stored, sent, or pushed to HubSpot."""
import re
from functools import lru_cache

from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import GUARD_BLOCKS, GUARD_CHECKS, GUARD_DURATION, timed
from app.guardrails import disable_telemetry
from app.guardrails.result import GuardResult
from app.guardrails.validators import NoUnauthorizedPromises
from app.schemas.ticket import Ticket

log = get_logger(__name__)

MAX_REPLY_SENTENCES = 4   # prompt asks for 3; allow a little slack


@lru_cache(maxsize=1)
def _reply_guard():
    from guardrails import Guard, OnFailAction

    guard = Guard(name="reply_guard").use(NoUnauthorizedPromises(on_fail=OnFailAction.EXCEPTION))
    # Optional: PII leak detection (guardrails hub install hub://guardrails/detect_pii)
    try:
        from guardrails.hub import DetectPII

        guard = guard.use(
            DetectPII(
                pii_entities=["CREDIT_CARD", "US_SSN", "IBAN_CODE"],
                on_fail=OnFailAction.EXCEPTION,
            )
        )
    except ImportError:
        log.warning("detect_pii validator not installed; skipping PII output check")
    return disable_telemetry(guard)


def _sentence_count(text: str) -> int:
    return len(re.findall(r"[.!?]+(?:\s|$)", text.strip()))


def _check_reply(text: str) -> GuardResult:
    if not text.strip():
        return GuardResult(False, text, "empty")
    if _sentence_count(text) > MAX_REPLY_SENTENCES:
        return GuardResult(False, text, "too_long")
    if "<data_" in text:
        return GuardResult(False, text, "leaked_marker")
    try:
        _reply_guard().validate(text)
    except Exception:
        return GuardResult(False, text, "unauthorized_claim")
    return GuardResult(True, text)


def _check_ticket(ticket: dict, source_text: str) -> GuardResult:
    try:
        parsed = Ticket.model_validate(ticket)
    except ValidationError:
        return GuardResult(False, "", "schema_invalid")
    if not parsed.issue.strip():
        return GuardResult(False, "", "empty_issue")
    if len(parsed.issue) > 1000:
        return GuardResult(False, "", "issue_too_long")
    # hallucination check: an extracted email must literally appear in the customer's message
    if parsed.email and parsed.email.lower() not in source_text.lower():
        return GuardResult(False, "", "invented_email")
    return GuardResult(True, "")


def _record(result: GuardResult) -> GuardResult:
    GUARD_CHECKS.labels("output", "pass" if result.passed else "block").inc()
    if not result.passed:
        GUARD_BLOCKS.labels("output", result.reason or "unknown").inc()
        log.warning("output rejected", extra={"reason": result.reason})
    return result


def check_reply(text: str) -> GuardResult:
    if not settings.guardrails_enabled:
        return GuardResult(True, text)
    with timed(GUARD_DURATION, stage="output"):
        result = _check_reply(text)
    return _record(result)


def check_ticket(ticket: dict, source_text: str) -> GuardResult:
    if not settings.guardrails_enabled:
        return GuardResult(True, "")
    with timed(GUARD_DURATION, stage="output"):
        result = _check_ticket(ticket, source_text)
    return _record(result)
