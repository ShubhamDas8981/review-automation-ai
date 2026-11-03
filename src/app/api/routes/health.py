import redis
from fastapi import APIRouter, HTTPException

from app.core.redis import r

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    try:
        r.ping()
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="redis unavailable")
    return {"status": "ok"}
