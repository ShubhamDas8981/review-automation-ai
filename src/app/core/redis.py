import redis

from app.core.config import settings

# One shared client (thread-safe, pooled). Connects lazily on first command.
r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
