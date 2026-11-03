from fastapi import HTTPException, status

from app.core.security import webhook_secret_is_valid


def require_webhook_secret(secret: str) -> None:
    """Dependency: `secret` is the {secret} path parameter of the webhook URL."""
    if not webhook_secret_is_valid(secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
