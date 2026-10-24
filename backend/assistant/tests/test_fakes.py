from asgiref.sync import async_to_sync
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.stream import ProtocolEvent

from assistant.tests.fakes import ToolCallingFakeModel


@tool
def echo(text: str) -> str:
    """Echo the text."""
    return text.upper()


def test_fake_streams_tool_calls() -> None:
    model = ToolCallingFakeModel(
        messages=iter(
            [
                AIMessage(content="Calling it.", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c1"}]),
                AIMessage(content="Done."),
            ]
        )
    )
    agent = create_agent(model, tools=[echo], checkpointer=InMemorySaver())

    async def run() -> list[ProtocolEvent]:
        stream = await agent.astream_events(
            {"messages": [{"role": "user", "content": "go"}]},
            {"configurable": {"thread_id": "t"}},
            version="v3",
        )
        return [e async for e in stream]

    events = async_to_sync(run)()

    finished = [e["params"]["data"] for e in events if e["method"] == "tools"]
    assert [d["event"] for d in finished] == ["tool-started", "tool-finished"]
    assert finished[1]["output"].content == "HI"
    final = [e for e in events if e["method"] == "values"][-1]["params"]["data"]["messages"]
    assert [m.type for m in final] == ["human", "ai", "tool", "ai"]
    assert final[-1].text == "Done."
