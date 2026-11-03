from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration lives here. Missing required values fail at startup."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM ---
    groq_api_key: str
    llm_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: float = 30.0

    # --- Redis / Celery ---
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/1"

    # --- Wati (WhatsApp) ---
    wati_api_base_url: str = "https://live-mt-server.wati.io"
    wati_api_token: str | None = None
    wati_channel_number: str = ""      # only needed if your Wati account has several numbers
    # old LEMIN_* names are still accepted so existing .env files keep working
    webhook_secret: str = Field(validation_alias=AliasChoices("webhook_secret", "lemin_webhook_secret"))
    watch_phone: str = Field(default="", validation_alias=AliasChoices("watch_phone", "lemin_watch_phone"))

    # --- HubSpot ---
    hubspot_token: str | None = None
    hubspot_api: str = "https://api.hubapi.com"
    hubspot_pipeline: str = "0"
    hubspot_stage: str = "1"
    hubspot_priority: str = "MEDIUM"
    hubspot_portal_id: str = ""
    hubspot_app_host: str = "app.hubspot.com"

    # --- TTLs (seconds) ---
    result_ttl: int = 3600
    seen_ttl: int = 7 * 24 * 3600
    sent_ttl: int = 7 * 24 * 3600
    ticket_ttl: int = 7 * 24 * 3600

    # --- Guardrails ---
    guardrails_enabled: bool = True
    guard_injection_threshold: float = 0.8
    guard_max_review_chars: int = 2000
    guard_on_fail_input: Literal["block", "flag"] = "block"

    # --- Logging / metrics ---
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    worker_metrics_port: int = 9100


settings = Settings()
