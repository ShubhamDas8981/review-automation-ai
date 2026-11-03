import uuid
from time import perf_counter

from fastapi import FastAPI, Request

from app.api.routes import health, metrics, reviews, webhooks
from app.core.logging import configure_logging, request_id_var
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS

_SKIP_METRICS = {"/metrics", "/health"}


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Review Automation")

    @app.middleware("http")
    async def observability(request: Request, call_next):
        rid = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:64]
        token = request_id_var.set(rid)
        start = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = rid
            return response
        finally:
            # route *template* (e.g. /webhooks/wati/{secret}): bounded labels, no secrets
            route = request.scope.get("route")
            path = getattr(route, "path", "unmatched")
            if path not in _SKIP_METRICS:
                HTTP_REQUESTS.labels(request.method, path, str(status_code)).inc()
                HTTP_DURATION.labels(request.method, path).observe(perf_counter() - start)
            request_id_var.reset(token)

    app.include_router(reviews.router)
    app.include_router(webhooks.router)
    app.include_router(health.router)
    app.include_router(metrics.router)
    return app


app = create_app()
