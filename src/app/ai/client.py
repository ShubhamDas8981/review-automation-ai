from functools import lru_cache

from groq import Groq

from app.core.config import settings
from app.core.metrics import LLM_DURATION, LLM_ERRORS, LLM_TOKENS, timed


@lru_cache(maxsize=1)
def get_client() -> Groq:
    return Groq(api_key=settings.groq_api_key, timeout=settings.llm_timeout_seconds)


def ask_llm(
    system_prompt: str,
    user_text: str,
    node: str,
    response_format: dict | None = None,
) -> str:
    """Single chat completion. `node` is a short fixed label used for metrics."""
    kwargs = {"response_format": response_format} if response_format else {}

    try:
        with timed(LLM_DURATION, node=node):
            response = get_client().chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                **kwargs,
            )
    except Exception as e:
        LLM_ERRORS.labels(node, type(e).__name__).inc()
        raise

    usage = getattr(response, "usage", None)
    if usage:
        LLM_TOKENS.labels(node, "prompt").inc(getattr(usage, "prompt_tokens", 0) or 0)
        LLM_TOKENS.labels(node, "completion").inc(getattr(usage, "completion_tokens", 0) or 0)

    return (response.choices[0].message.content or "").strip()
