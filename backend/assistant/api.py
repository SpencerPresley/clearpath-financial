from django.http import HttpRequest
from ninja import Router, Status

from assistant.schemas import AssistantApprovalIn, AssistantMessageIn, AssistantStreamEventOut, AssistantThreadOut
from core.errors import NotImplementedYet
from core.schemas import STUB_ERRORS

router = Router(tags=["assistant"])

_SSE = (
    "Server-sent events (`text/event-stream`). Each `data:` line is one AssistantStreamEventOut as JSON; the "
    "stream ends after a `done` or `error` event."
)


@router.post(
    "/assistant/threads", response={201: AssistantThreadOut, **STUB_ERRORS}, operation_id="createAssistantThread"
)
def create_thread(request: HttpRequest) -> Status[AssistantThreadOut]:
    """[workstream K]"""
    raise NotImplementedYet("the assistant")


@router.get(
    "/assistant/threads/{thread_id}",
    response={200: AssistantThreadOut, **STUB_ERRORS},
    operation_id="getAssistantThread",
)
def get_thread(request: HttpRequest, thread_id: str) -> AssistantThreadOut:
    """[workstream K]"""
    raise NotImplementedYet("the assistant")


@router.post(
    "/assistant/threads/{thread_id}/messages",
    response={200: AssistantStreamEventOut, **STUB_ERRORS},
    operation_id="streamAssistantReply",
    description=_SSE,
)
def stream_reply(request: HttpRequest, thread_id: str, body: AssistantMessageIn) -> AssistantStreamEventOut:  # pyrefly: ignore[bad-return]
    """Send a message and stream the reply. [workstream K]"""
    raise NotImplementedYet("the assistant")


@router.post(
    "/assistant/threads/{thread_id}/approvals/{interrupt_id}",
    response={200: AssistantStreamEventOut, **STUB_ERRORS},
    operation_id="resolveAssistantApproval",
    description=_SSE,
)
def resolve_approval(  # pyrefly: ignore[bad-return]
    request: HttpRequest, thread_id: str, interrupt_id: str, body: AssistantApprovalIn
) -> AssistantStreamEventOut:
    """Approve, edit, or reject a paused `send_email`; streams the resumed run. [workstream K]"""
    raise NotImplementedYet("the assistant")
