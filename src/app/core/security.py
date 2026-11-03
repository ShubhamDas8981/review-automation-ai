import hmac

from app.core.config import settings


def secrets_match(provided: str, expected: str) -> bool:
    """Constant-time comparison (avoids timing attacks)."""
    return hmac.compare_digest(provided.encode(), expected.encode())


def webhook_secret_is_valid(provided: str) -> bool:
    return secrets_match(provided, settings.webhook_secret)
