from dataclasses import dataclass


@dataclass
class GuardResult:
    passed: bool
    text: str = ""
    reason: str | None = None   # short fixed code, safe to use as a metric label
