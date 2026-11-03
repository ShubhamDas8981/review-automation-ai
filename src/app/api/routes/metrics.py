from fastapi import APIRouter, Response

from app.core.metrics import render_metrics

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics():
    body, content_type = render_metrics()
    return Response(body, media_type=content_type)
