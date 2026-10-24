"""Model construction, in one place.

Phase 2 reads the model name from settings and passes it in. Nothing here reads the environment except
ChatAnthropic itself, which falls back to `ANTHROPIC_API_KEY` when `api_key` is None.

- **No temperature.** Haiku 5.5 returns a 400 for any temperature other than 1 (Haiku 5.5 migration guide,
  "Remove sampling parameters"). So there's no determinism knob, and the eval repeats runs instead.
- **Retries.** These happen in the Anthropic SDK: 408, 409, 429, 5xx and connection errors, exponential backoff
  from 0.5 s capped at 8 s, `retry-after` honored (anthropic `_base_client.py`, `_constants.py`). The count is
  capped at MAX_RETRIES, and each attempt is capped at TIMEOUT_SECONDS, so the worst case is about
  4 x 60 s plus backoff.
- **Forced tool choice.** It works on Haiku 5.5: the reply starts with the tool call and skips thinking.
  - The models below reject forced tool choice with a 400. They get `auto`, strict tool use (the docs'
    recommendation for these models), the prompt's "call report_findings" instruction, and a larger token cap,
    because their thinking spends `max_tokens` too.
  - That path is untested against the live API.
"""

from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr

DEFAULT_MODEL = "claude-haiku-5-5"
MAX_TOKENS = 2048  # ~15 findings at ~120 tokens each; truncation shows up as output_valid=False
MAX_TOKENS_WITH_THINKING = 8192  # models that can't force the tool think first, and thinking counts here
MAX_RETRIES = 3
TIMEOUT_SECONDS = 60.0

_NO_FORCED_TOOL_CHOICE = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-mythos-5-1")


def forces_tool_choice(model_name: str) -> bool:
    return not model_name.startswith(_NO_FORCED_TOOL_CHOICE)


def get_review_model(model_name: str = DEFAULT_MODEL, *, api_key: str | None = None) -> ChatAnthropic:
    max_tokens = MAX_TOKENS if forces_tool_choice(model_name) else MAX_TOKENS_WITH_THINKING
    if api_key is None:
        return ChatAnthropic(model=model_name, max_tokens=max_tokens, max_retries=MAX_RETRIES, timeout=TIMEOUT_SECONDS)
    return ChatAnthropic(
        model=model_name,
        max_tokens=max_tokens,
        max_retries=MAX_RETRIES,
        timeout=TIMEOUT_SECONDS,
        api_key=SecretStr(api_key),
    )
