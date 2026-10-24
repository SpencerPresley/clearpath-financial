"""Assistant endpoints. The streaming operations are sync: authentication, ownership (another user's thread is
a 404), body validation, the pending-approval check and the run lock all happen before the response starts,
so those failures are ordinary JSON errors. The body is an async iterator Django serves natively under ASGI."""

from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from asgiref.sync import async_to_sync
from django.http import HttpRequest, StreamingHttpResponse
from ninja import Router, Status

from accounts.api import current_user
from accounts.models import User
from assistant import runs, selectors, services
from assistant.email import check_recipients
from assistant.schemas import (
    ApprovalResponseIn,
    ApproveIn,
    AssistantRunIn,
    AssistantThreadOut,
    AssistantThreadStateOut,
    EditIn,
    RejectIn,
)
from assistant.tools import parse_item_key
from core.errors import Conflict, InvalidInput
from core.schemas import ERRORS
from reviews.models import ReviewItem
from reviews.selectors import get_item_row

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
PENDING_APPROVAL: Final = "An email is waiting for your approval in this thread. Approve, edit or reject it first."
NOT_PENDING: Final = "That approval is no longer pending."


def _sse(body: AsyncIterator[bytes]) -> StreamingHttpResponse:
    response = StreamingHttpResponse(body, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response


def _locked(viewer: User, thread_id: UUID, check: Callable[[], None]) -> datetime:
    """Take the run lock, then run `check` under it; a failed check gives the lock back."""
    claimed_at = services.claim_run(thread_id=thread_id, owner=viewer)
    try:
        check()
    except BaseException:
        services.release_run(thread_id=thread_id, claimed_at=claimed_at)
        raise
    return claimed_at


def _pending(viewer: User, thread_id: UUID) -> set[str]:
    return async_to_sync(runs.pending_interrupt_ids)(thread_id=thread_id, viewer=viewer)


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
    response={200: AssistantThreadStateOut, **ERRORS},
    operation_id="getAssistantThreadState",
)
def get_thread_state(request: HttpRequest, thread_id: UUID) -> AssistantThreadStateOut:
    """The checkpointed conversation and any pending approval (hydrates the panel)."""
    viewer = current_user(request)
    selectors.owned_thread(owner=viewer, thread_id=thread_id)
    return async_to_sync(runs.read_state)(thread_id=thread_id, viewer=viewer)


@router.post(
    "/assistant/threads/{uuid:thread_id}/runs",
    response={200: None, **ERRORS},
    operation_id="startAssistantRun",
    description=_SSE,
    openapi_extra=_SSE_RESPONSE,
)
def start_run(request: HttpRequest, thread_id: UUID, body: AssistantRunIn) -> StreamingHttpResponse:
    """Send a message and stream the reply. 409 while another reply is running or an email awaits approval."""
    viewer = current_user(request)
    selectors.owned_thread(owner=viewer, thread_id=thread_id)
    item = get_item_row(item_id=body.item_id) if body.item_id is not None else None

    def no_pending_approval() -> None:
        # A new message under a paused send_email would leave a tool call without its result.
        if _pending(viewer, thread_id):
            raise Conflict(PENDING_APPROVAL)

    claimed_at = _locked(viewer, thread_id, no_pending_approval)
    command = runs.StartRun(message_id=body.message.id, content=body.message.content, item=item)
    return _sse(runs.stream_run(thread_id=thread_id, viewer=viewer, command=command, claimed_at=claimed_at))


def hitl_decision(body: ApproveIn | EditIn | RejectIn) -> dict[str, Any]:
    """The HumanInTheLoopMiddleware decision for a validated answer. An edit is checked here first (the
    allowlist middleware only saw the model's draft): outside recipients are a 422 on `to`."""
    if isinstance(body, ApproveIn):
        return {"type": "approve"}
    if isinstance(body, EditIn):
        args = body.edited_action.args
        to = check_recipients(args.to)
        if args.item_key is not None:
            item_id = parse_item_key(args.item_key)
            if item_id is None or not ReviewItem.objects.filter(pk=item_id).exists():
                raise InvalidInput.for_field("item_key", f"No item {args.item_key}.")
        edited = {"to": list(to), "subject": args.subject, "body": args.body, "item_key": args.item_key}
        return {"type": "edit", "edited_action": {"name": "send_email", "args": edited}}
    return {"type": "reject", "message": body.message.strip() or runs.REJECT_DEFAULT}


@router.post(
    "/assistant/threads/{uuid:thread_id}/interrupts/{interrupt_id}",
    response={200: None, **ERRORS},
    operation_id="respondToAssistantInterrupt",
    description=_SSE,
    openapi_extra=_SSE_RESPONSE,
)
def respond_to_interrupt(
    request: HttpRequest, thread_id: UUID, interrupt_id: str, body: ApprovalResponseIn
) -> StreamingHttpResponse:
    """Approve, edit, or reject a paused `send_email`, then stream the resumed run. 409 if that approval was
    already answered (a double click, another tab); 422 on `to` if an edit names an outside address."""
    viewer = current_user(request)
    selectors.owned_thread(owner=viewer, thread_id=thread_id)
    decision = hitl_decision(body)

    def still_pending() -> None:
        # Checked under the lock: once we hold it, nothing else can answer this interrupt before we resume.
        if interrupt_id not in _pending(viewer, thread_id):
            raise Conflict(NOT_PENDING)

    claimed_at = _locked(viewer, thread_id, still_pending)
    command = runs.Resume(interrupt_id=interrupt_id, decision=decision)
    return _sse(runs.stream_run(thread_id=thread_id, viewer=viewer, command=command, claimed_at=claimed_at))
