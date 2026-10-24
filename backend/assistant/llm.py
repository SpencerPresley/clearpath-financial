"""The assistant's chat model, built per run from settings (D's construction rules, `checks/llm/client.py`).

- No temperature/top_p/top_k: Haiku 5.5 returns a 400 for any temperature other than 1.
- Retries happen in the Anthropic SDK (408/409/429/5xx/connection, exponential backoff, `retry-after`); each
  attempt is capped at 60 s.
- Tool choice stays `auto`: the assistant answers in prose and calls tools only when it needs data.
- The key comes only from settings. ChatAnthropic would fall back to `ANTHROPIC_API_KEY` on its own; refusing
  instead keeps "which key is this using?" answerable from one place.
"""

from django.conf import settings
from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr

MAX_TOKENS = 2048
MAX_RETRIES = 3
TIMEOUT_SECONDS = 60.0


class AssistantNotConfigured(Exception):  # noqa: N818  # reads as a state, like Django's ImproperlyConfigured
    def __init__(self) -> None:
        super().__init__("The assistant isn't configured (no API key).")


def get_assistant_model() -> ChatAnthropic:
    key = settings.ASSISTANT_ANTHROPIC_API_KEY
    if not key:
        raise AssistantNotConfigured
    return ChatAnthropic(
        model=settings.ASSISTANT_MODEL,
        max_tokens=MAX_TOKENS,
        max_retries=MAX_RETRIES,
        timeout=TIMEOUT_SECONDS,
        api_key=SecretStr(key),
    )
