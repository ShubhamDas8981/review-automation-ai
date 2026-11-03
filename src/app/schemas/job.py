from enum import StrEnum

from pydantic import BaseModel


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRYING = "retrying"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"            # input guardrail rejected the message
    NEEDS_REVIEW = "needs_review"  # output guardrail rejected the LLM result


class JobAccepted(BaseModel):
    job_id: str
    status: str
