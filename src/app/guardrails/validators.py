"""Custom Guardrails AI validators for this business."""
import re

try:
    from guardrails.validators import FailResult, PassResult, Validator, register_validator
except ImportError:  # newer guardrails-ai layouts
    from guardrails.validator_base import (  # type: ignore
        FailResult,
        PassResult,
        Validator,
        register_validator,
    )

_PROMISES = re.compile(
    r"\bwe(?:'ve|\s+have)\s+(?:already\s+)?(?:issued|processed|refunded|credited|cancell?ed)\b"
    r"|\b(?:your\s+)?refund\s+(?:has\s+been|is\s+on\s+its\s+way|will\s+be)\b"
    r"|\byour\s+account\s+(?:has\s+been|was)\s+(?:credited|closed|upgraded)\b",
    re.IGNORECASE,
)


def find_unauthorized_promise(text: str) -> bool:
    return bool(_PROMISES.search(text))


@register_validator(name="review-automation/no_unauthorized_promises", data_type="string")
class NoUnauthorizedPromises(Validator):
    """A reply must not claim refunds or actions that have not happened."""

    def validate(self, value, metadata):
        if find_unauthorized_promise(value):
            return FailResult(error_message="Reply claims an action that did not occur")
        return PassResult()
