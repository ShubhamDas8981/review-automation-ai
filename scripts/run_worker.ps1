# Windows: Celery's prefork pool is not supported, so use the solo pool.
uv run celery -A app.workers.celery_app worker -Q review_jobs -l info --pool=solo
