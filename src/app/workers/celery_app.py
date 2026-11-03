import os
import time

from celery import Celery
from celery.signals import (
    setup_logging,
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    worker_process_shutdown,
    worker_ready,
)
from prometheus_client import multiprocess, start_http_server

from app.core.config import settings
from app.core.logging import configure_logging, get_logger, job_id_var
from app.core.metrics import (
    TASK_DURATION,
    TASK_FAILURES,
    TASK_RETRIES,
    metrics_registry,
)

log = get_logger(__name__)

celery_app = Celery(
    "reviews",
    broker=settings.celery_broker_url,
    include=[
        "app.workers.tasks.review",
        "app.workers.tasks.hubspot",
        "app.workers.tasks.messaging",
    ],
)
app = celery_app  # alias so `celery -A app.workers.celery_app` finds it

celery_app.conf.update(
    task_default_queue="review_jobs",
    task_ignore_result=True,              # results live in our own job:<id> keys
    task_acks_late=True,                  # re-deliver if the worker dies mid-job
    worker_prefetch_multiplier=1,         # one slow LLM call shouldn't hog queued tasks
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    worker_hijack_root_logger=False,      # keep our logging config
    timezone="UTC",
)

_task_starts: dict[str, float] = {}


# ---------- logging ----------
@setup_logging.connect
def _configure_celery_logging(**kwargs):
    configure_logging()


# ---------- per-task context + metrics ----------
@task_prerun.connect
def _task_start(task_id=None, args=None, **kwargs):
    # process_review_task gets a dict; the other tasks get job_id first
    first = args[0] if args else None
    job_id_var.set(first.get("job_id") if isinstance(first, dict) else first)
    _task_starts[task_id] = time.perf_counter()


@task_postrun.connect
def _task_end(task_id=None, task=None, **kwargs):
    started = _task_starts.pop(task_id, None)
    if started is not None and task is not None:
        TASK_DURATION.labels(task.name).observe(time.perf_counter() - started)
    job_id_var.set(None)


@task_retry.connect
def _task_retry(sender=None, **kwargs):
    if sender is not None:
        TASK_RETRIES.labels(sender.name).inc()


@task_failure.connect
def _task_failure(sender=None, **kwargs):
    if sender is not None:
        TASK_FAILURES.labels(sender.name).inc()


# ---------- Prometheus endpoint for the worker ----------
@worker_ready.connect
def _start_metrics_server(**kwargs):
    try:
        start_http_server(settings.worker_metrics_port, registry=metrics_registry())
        log.info("worker metrics server started", extra={"port": settings.worker_metrics_port})
    except OSError:
        log.warning("worker metrics port in use; metrics endpoint not started")


@worker_process_shutdown.connect
def _cleanup_dead_process(pid=None, **kwargs):
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        multiprocess.mark_process_dead(pid)
