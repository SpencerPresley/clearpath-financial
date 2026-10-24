from uuid import UUID

from django.http import HttpRequest, StreamingHttpResponse
from ninja import Router, Status

from accounts.api import current_user
from assistant import selectors, services
from assistant.schemas import ApprovalResponseIn, AssistantRunIn, AssistantThreadOut, AssistantThreadStateOut
from core.errors import NotImplementedYet
from core.schemas import ERRORS, STUB_ERRORS

router = Router(tags=["assistant"])

_SSE = (
    "Streams the run as Server-Sent Events (`text/event-stream`): each `data:` line is one LangChain Agent "
    "Streaming Protocol event (`lifecycle`, `messages`, `tools`, `values`, `input.requested`); `: keepalive` "
    "comments every 15 s. Ends after a root `lifecycle` event of `completed`, `interrupted` (an email awaits "
    "approval) or `failed`. Errors before the stream starts are JSON. Closing the connection cancels the run."
)
_SSE_RESPONSE = {
    "responses": {
        200: {"description": "Protocol events.", "content": {"text/event-stream": {"schema": {"type": "string"}}}}
    }
}


@router.get(
    "/assistant/threads", response={200: list[AssistantThreadOut], **ERRORS}, operation_id="listAssistantThreads"
)
def list_threads(request: HttpRequest) -> list[selectors.ThreadRow]:
    """Your assistant threads, most recent activity first."""
    return list(selectors.list_threads(owner=current_user(request)))


@router.post("/assistant/threads", response={201: AssistantThreadOut, **ERRORS}, operation_id="createAssistantThread")
def create_thread(request: HttpRequest) -> Status[selectors.ThreadRow]:
    thread = services.create_thread(owner=current_user(request))
    return Status(201, selectors.thread_row(thread))


@router.get(
    "/assistant/threads/{uuid:thread_id}",
    response={200: AssistantThreadOut, **ERRORS},
    operation_id="getAssistantThread",
)
def get_thread(request: HttpRequest, thread_id: UUID) -> selectors.ThreadRow:
    return selectors.get_thread(owner=current_user(request), thread_id=thread_id)


@router.get(
    "/assistant/threads/{uuid:thread_id}/state",
    response={200: AssistantThreadStateOut, **STUB_ERRORS},
    operation_id="getAssistantThreadState",
)
def get_thread_state(request: HttpRequest, thread_id: UUID) -> AssistantThreadStateOut:
    """The checkpointed conversation and any pending approval (hydrates the panel). [workstream K]"""
    raise NotImplementedYet("the assistant")


@router.post(
    "/assistant/threads/{uuid:thread_id}/runs",
    response={200: None, **STUB_ERRORS},
    operation_id="startAssistantRun",
    description=_SSE,
    openapi_extra=_SSE_RESPONSE,
)
def start_run(request: HttpRequest, thread_id: UUID, body: AssistantRunIn) -> StreamingHttpResponse:
    """Send a message and stream the reply. [workstream K]"""
    raise NotImplementedYet("the assistant")


@router.post(
    "/assistant/threads/{uuid:thread_id}/interrupts/{interrupt_id}",
    response={200: None, **STUB_ERRORS},
    operation_id="respondToAssistantInterrupt",
    description=_SSE,
    openapi_extra=_SSE_RESPONSE,
)
def respond_to_interrupt(
    request: HttpRequest, thread_id: UUID, interrupt_id: str, body: ApprovalResponseIn
) -> StreamingHttpResponse:
    """Approve, edit, or reject a paused `send_email`, then stream the resumed run. [workstream K]"""
    raise NotImplementedYet("the assistant")
