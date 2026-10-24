"""Model construction and the request ChatAnthropic would send, built offline (no network)."""

import pytest
from django.test import override_settings
from langchain_core.messages import HumanMessage, SystemMessage

from assistant.llm import AssistantNotConfigured, get_assistant_model


@override_settings(ASSISTANT_ANTHROPIC_API_KEY="test-key", ASSISTANT_MODEL="claude-haiku-5-5")
def test_model_has_no_sampling_params() -> None:
    model = get_assistant_model()

    assert model.model == "claude-haiku-5-5"
    assert model.max_tokens == 2048
    assert model.max_retries == 3
    assert model.default_request_timeout == 60
    assert model.anthropic_api_key.get_secret_value() == "test-key"
    payload = model._get_request_payload([SystemMessage("s"), HumanMessage("hi")])
    for key in ("temperature", "top_p", "top_k", "thinking"):
        assert key not in payload
    assert payload["max_tokens"] == 2048


@override_settings(ASSISTANT_ANTHROPIC_API_KEY=None)
def test_missing_key_is_reported_not_guessed_from_the_environment() -> None:
    with pytest.raises(AssistantNotConfigured, match="no API key"):
        get_assistant_model()
