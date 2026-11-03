"""Prometheus metric definitions. Never use job_id, phone, email or wamid as a label."""
import os
from contextlib import contextmanager
from time import perf_counter

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

# ---------- HTTP ----------
HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP latency", ["method", "route"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

# ---------- Business ----------
REVIEWS_RECEIVED = Counter("reviews_received_total", "Reviews enqueued", ["source"])
WEBHOOK_SKIPPED = Counter("webhook_messages_skipped_total", "Skipped inbound messages", ["reason"])
JOBS_FINISHED = Counter("jobs_finished_total", "Jobs by final status", ["status"])
SENTIMENT = Counter("review_sentiment_total", "Classified reviews", ["sentiment"])

# ---------- Guardrails ----------
GUARD_CHECKS = Counter("guardrail_checks_total", "Guard checks", ["stage", "outcome"])
GUARD_BLOCKS = Counter("guardrail_blocks_total", "Guard blocks", ["stage", "reason"])
GUARD_DURATION = Histogram(
    "guardrail_check_seconds", "Guard latency", ["stage"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

# ---------- LLM ----------
LLM_DURATION = Histogram(
    "llm_request_seconds", "LLM call latency", ["node"],
    buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 30),
)
LLM_ERRORS = Counter("llm_errors_total", "LLM call failures", ["node", "error"])
LLM_TOKENS = Counter("llm_tokens_total", "Tokens used", ["node", "type"])

# ---------- External services ----------
EXTERNAL_REQUESTS = Counter("external_requests_total", "Outbound calls", ["service", "outcome"])
EXTERNAL_DURATION = Histogram(
    "external_request_seconds", "Outbound latency", ["service"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20),
)

# ---------- Celery ----------
TASK_DURATION = Histogram(
    "celery_task_seconds", "Task runtime", ["task"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
TASK_RETRIES = Counter("celery_task_retries_total", "Task retries", ["task"])
TASK_FAILURES = Counter("celery_task_failures_total", "Task failures", ["task"])


@contextmanager
def timed(histogram: Histogram, **labels):
    start = perf_counter()
    try:
        yield
    finally:
        histogram.labels(**labels).observe(perf_counter() - start)


def metrics_registry() -> CollectorRegistry:
    """Multiprocess-aware when PROMETHEUS_MULTIPROC_DIR is set."""
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    return REGISTRY


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(metrics_registry()), CONTENT_TYPE_LATEST
