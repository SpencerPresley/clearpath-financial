"""A scripted chat model whose tool calls survive `astream_events(version="v3")`.

v3 drives the model through `_stream`, and `GenericFakeChatModel._stream` streams only `content` (and the
legacy `additional_kwargs.function_call`), so its tool calls vanish (spike finding 6). This one streams the
content word by word, then one final chunk carrying every tool call as `tool_call_chunks`.
"""

import json
import time
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool


class ToolCallingFakeModel(GenericFakeChatModel):
    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable | BaseTool],
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        message = next(self.messages)
        if isinstance(message, str):
            message = AIMessage(content=message)
        text = message.text
        words = text.split(" ") if text else []
        for i, word in enumerate(words):
            token = word if i == len(words) - 1 else f"{word} "
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=token, id=message.id))
            if run_manager:
                run_manager.on_llm_new_token(token, chunk=chunk)
            yield chunk
        tool_call_chunks = [
            {
                "name": call["name"],
                "args": json.dumps(call["args"]),
                "id": call["id"],
                "index": i,
                "type": "tool_call_chunk",
            }
            for i, call in enumerate(getattr(message, "tool_calls", []))
        ]
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                id=message.id,
                tool_call_chunks=tool_call_chunks,  # pyrefly: ignore[bad-argument-type]
                chunk_position="last",
            )
        )


def scripted(*messages: AIMessage | str) -> ToolCallingFakeModel:
    return ToolCallingFakeModel(messages=iter(messages))


class FailingModel(ToolCallingFakeModel):
    """Stands in for the provider failing after the SDK's retries; the error text must never reach the user."""

    messages: Iterator[AIMessage | str] = iter(())

    def _stream(self, *args: Any, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        raise RuntimeError("upstream 529 overloaded_error: request_id=req_secret body={...}")


class SlowModel(ToolCallingFakeModel):
    """Pauses before each reply, so the stream sits idle long enough for a keepalive."""

    delay: float = 0.3

    def _stream(self, *args: Any, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        time.sleep(self.delay)  # runs in langchain's executor thread, not on the event loop
        yield from super()._stream(*args, **kwargs)
