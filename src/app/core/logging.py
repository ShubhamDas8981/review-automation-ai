import json
import logging
import logging.config
import re
from contextvars import ContextVar
from datetime import datetime, timezone

from app.core.config import settings

# ---------------------------
# Per-request / per-task context
# ---------------------------
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)

# ---------------------------
# Redaction (safety net: never log customer data on purpose)
# ---------------------------
_EMAIL = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PHONE = re.compile(r"(?<![\w-])\+?\d[\d\s\-()]{8,}\d(?![\w-])")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE)
_SECRET_URL = re.compile(r"(/webhooks/[A-Za-z]+/)[^/\s\"']+")
_API_KEY = re.compile(r"\b(?:gsk_|pat-|sk-)[A-Za-z0-9_\-]{8,}")


def _mask_phone(m: re.Match) -> str:
    raw = m.group()
    n = re.sub(r"\D", "", raw)
    if not 10 <= len(n) <= 15 or _DATE.fullmatch(raw.strip()):
        return raw
    return "***" + n[-4:]


def redact(text: str) -> str:
    text = _EMAIL.sub(r"\1***\2", text)
    text = _PHONE.sub(_mask_phone, text)
    text = _BEARER.sub(r"\1[REDACTED]", text)
    text = _SECRET_URL.sub(r"\1[REDACTED]", text)
    text = _API_KEY.sub("[REDACTED_KEY]", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        record.job_id = job_id_var.get() or "-"
        return True


# ---------------------------
# Formatters
# ---------------------------
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class RedactingFormatter(logging.Formatter):
    """Tracebacks are formatted after filters run, so redact them here."""

    def formatException(self, ei) -> str:
        return redact(super().formatException(ei))


class JsonFormatter(RedactingFormatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "job_id": getattr(record, "job_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload and not key.startswith("_"):
                payload[key] = redact(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


# ---------------------------
# Setup
# ---------------------------
def configure_logging() -> None:
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": ContextFilter},
            "redact": {"()": RedactingFilter},
        },
        "formatters": {
            "console": {
                "()": RedactingFormatter,
                "fmt": "%(asctime)s %(levelname)-8s [%(job_id).8s|%(request_id).8s] "
                       "%(name)s: %(message)s",
                "datefmt": "%H:%M:%S",
            },
            "json": {"()": JsonFormatter},
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": settings.log_format,
                "filters": ["context", "redact"],
            },
        },
        "root": {"level": settings.log_level, "handlers": ["stdout"]},
        "loggers": {
            "uvicorn": {"level": "INFO", "handlers": [], "propagate": True},
            "uvicorn.error": {"level": "INFO", "handlers": [], "propagate": True},
            "uvicorn.access": {"level": "INFO", "handlers": [], "propagate": True},
            "celery": {"level": "INFO", "handlers": [], "propagate": True},
            # these log full URLs, which contain identifiers
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
            "groq": {"level": "WARNING"},
        },
    })


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
