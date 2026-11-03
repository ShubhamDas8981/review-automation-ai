#!/usr/bin/env bash
# Linux/macOS/Docker: prefork pool + Prometheus multiprocess mode
set -euo pipefail
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prom}"
rm -rf "$PROMETHEUS_MULTIPROC_DIR" && mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
exec uv run celery -A app.workers.celery_app worker -Q review_jobs -l info "$@"
