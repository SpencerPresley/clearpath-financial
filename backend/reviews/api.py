"""Items, decisions, and library routers. Thin: parse, call a service or selector, return a schema.
Stubs validate input and raise NotImplementedYet; the owning workstream is named in each."""

from typing import Annotated

from django.http import FileResponse, HttpRequest
from ninja import File, Form, Query, Router, Status, UploadedFile

from accounts.api import current_user
from audit.schemas import ItemHistoryOut
from core.clock import SYSTEM_CLOCK
from core.domain import AttachmentKind, ItemStatus
from core.errors import NotImplementedYet
from core.schemas import ERRORS, STUB_ERRORS, PageLimit
from reviews import records, search, selectors, services
from reviews.filters import ItemFilter, ItemSort
from reviews.schemas import (
    AssignIn,
    AttachmentOut,
    BulkAssignIn,
    BulkFastTrackIn,
    BulkResultOut,
    CommentIn,
    CommentOut,
    DecisionIn,
    DecisionOut,
    FetchCopyIn,
    FetchedCopyOut,
    ItemDetailOut,
    ItemPageOut,
    ItemRowOut,
    ItemUpdateIn,
    NewRoundIn,
    PlacementIn,
    PlacementOut,
    PlacementUpdateIn,
    PullIn,
    QueueStatsOut,
    ReaffirmIn,
    ResubmitIn,
    SavedViewIn,
    SavedViewOut,
    SearchResultsOut,
    SubmitItemIn,
    VersionDiffOut,
    VersionOut,
    VersionSummaryOut,
)

items_router = Router(tags=["items"])
decisions_router = Router(tags=["decisions"])
library_router = Router(tags=["library"])


# --- queue -----------------------------------------------------------------------------------------------------


@items_router.get("/items", response={200: ItemPageOut, **ERRORS}, operation_id="listItems")
def list_items(
    request: HttpRequest,
    filters: Query[ItemFilter],
    sort: ItemSort = ItemSort.QUEUE,
    cursor: str | None = None,
    limit: PageLimit = 50,
) -> selectors.ItemPage:
    """The queue and every filtered list of items, in `sort` order, one keyset page at a time."""
    return selectors.list_items(viewer=current_user(request), filters=filters, sort=sort, cursor=cursor, limit=limit)


@items_router.get("/items/stats", response={200: QueueStatsOut, **ERRORS}, operation_id="getQueueStats")
def queue_stats(request: HttpRequest) -> selectors.QueueStats:
    return selectors.queue_stats(viewer=current_user(request))


# --- intake ----------------------------------------------------------------------------------------------------


@items_router.post("/items", response={201: ItemDetailOut, **ERRORS}, operation_id="submitItem")
def submit_item(request: HttpRequest, body: SubmitItemIn) -> Status[records.ItemDetail]:
    result = services.submit_item(
        actor=current_user(request),
        data=services.SubmitItemInput(
            title=body.title,
            product=body.product,
            channel=body.channel,
            markets=tuple(body.markets),
            content_text=body.content_text,
            planned_first_run=body.planned_first_run,
            planned_last_run=body.planned_last_run,
            partner_id=body.partner_id,
            is_prescreen=body.is_prescreen,
            source_url=body.source_url,
            tags=tuple(body.tags),
        ),
    )
    return Status(201, records.get_item_detail(item_id=result.item_id))


@items_router.post("/items/fetch-url", response={200: FetchedCopyOut, **STUB_ERRORS}, operation_id="fetchCopyFromUrl")
def fetch_copy(request: HttpRequest, body: FetchCopyIn) -> FetchedCopyOut:
    """Fetch a page's visible text to paste as copy. [workstream I/M: httpx + text extraction]"""
    raise NotImplementedYet("fetching copy from a URL")


# --- item record -----------------------------------------------------------------------------------------------


@items_router.get("/items/{int:item_id}", response={200: ItemDetailOut, **ERRORS}, operation_id="getItem")
def get_item(request: HttpRequest, item_id: int) -> records.ItemDetail:
    return records.get_item_detail(item_id=item_id)


@items_router.patch("/items/{int:item_id}", response={200: ItemRowOut, **ERRORS}, operation_id="updateItem")
def update_item(request: HttpRequest, item_id: int, body: ItemUpdateIn) -> selectors.ItemRow:
    """Inline edits from the queue: tags, notes, risk tier."""
    viewer = current_user(request)
    services.update_item_fields(
        actor=viewer,
        item_id=item_id,
        changes=services.ItemFieldChanges(
            tags=tuple(body.tags) if body.tags is not None else None, notes=body.notes, risk_tier=body.risk_tier
        ),
    )
    return selectors.get_item_row(item_id=item_id)


@items_router.get(
    "/items/{int:item_id}/versions", response={200: list[VersionSummaryOut], **ERRORS}, operation_id="listVersions"
)
def list_versions(request: HttpRequest, item_id: int) -> list[records.VersionSummary]:
    return list(records.list_versions(item_id=item_id))


@items_router.post(
    "/items/{int:item_id}/versions", response={201: VersionOut, **STUB_ERRORS}, operation_id="resubmitItem"
)
def resubmit_item(request: HttpRequest, item_id: int, body: ResubmitIn) -> Status[VersionOut]:
    """Submit v+1 after changes were requested; bumps the round. [workstream E]"""
    raise NotImplementedYet("resubmitting")


@items_router.get(
    "/items/{int:item_id}/versions/{int:n}", response={200: VersionOut, **ERRORS}, operation_id="getVersion"
)
def get_version(request: HttpRequest, item_id: int, n: int) -> records.VersionDetail:
    return records.get_version(item_id=item_id, n=n)


@items_router.get("/items/{int:item_id}/diff", response={200: VersionDiffOut, **ERRORS}, operation_id="getVersionDiff")
def get_diff(
    request: HttpRequest, item_id: int, from_n: Annotated[int, Query(ge=1)], to_n: Annotated[int, Query(ge=1)]
) -> records.VersionDiff:
    return records.version_diff(item_id=item_id, from_n=from_n, to_n=to_n)


@items_router.get(
    "/items/{int:item_id}/history", response={200: ItemHistoryOut, **ERRORS}, operation_id="getItemHistory"
)
def get_history(request: HttpRequest, item_id: int) -> dict[str, object]:
    return {"entries": records.item_history(item_id=item_id)}


@items_router.post(
    "/items/{int:item_id}/new-round", response={201: VersionOut, **STUB_ERRORS}, operation_id="startNewRound"
)
def start_new_round(request: HttpRequest, item_id: int, body: NewRoundIn) -> Status[VersionOut]:
    """withdrawn or expired -> draft v+1 -> submitted. [workstream E]"""
    raise NotImplementedYet("starting a new round")


# --- comments --------------------------------------------------------------------------------------------------


@items_router.get(
    "/items/{int:item_id}/comments", response={200: list[CommentOut], **ERRORS}, operation_id="listComments"
)
def list_comments(request: HttpRequest, item_id: int, version_n: int | None = None) -> list[records.CommentRow]:
    return list(records.list_comments(item_id=item_id, version_n=version_n))


@items_router.post("/items/{int:item_id}/comments", response={201: CommentOut, **ERRORS}, operation_id="addComment")
def add_comment(request: HttpRequest, item_id: int, body: CommentIn) -> Status[records.CommentRow]:
    comment_id = services.add_comment(
        actor=current_user(request),
        item_id=item_id,
        data=services.NewComment(
            body=body.body,
            version_n=body.version_n,
            span_start=body.span_start,
            span_end=body.span_end,
            mention_user_ids=tuple(body.mention_user_ids),
        ),
    )
    return Status(201, next(c for c in records.list_comments(item_id=item_id) if c.id == comment_id))


# --- attachments -----------------------------------------------------------------------------------------------


@items_router.get(
    "/items/{int:item_id}/attachments",
    response={200: list[AttachmentOut], **ERRORS},
    operation_id="listItemAttachments",
)
def list_item_attachments(request: HttpRequest, item_id: int) -> list[records.AttachmentRow]:
    return list(records.list_item_attachments(item_id=item_id))


@items_router.post(
    "/items/{int:item_id}/attachments", response={201: AttachmentOut, **ERRORS}, operation_id="uploadItemAttachment"
)
def upload_item_attachment(
    request: HttpRequest, item_id: int, kind: Form[AttachmentKind], file: File[UploadedFile]
) -> Status[records.AttachmentRow]:
    ref = services.add_attachment(
        actor=current_user(request), owner=services.AttachmentOwner(kind="item", id=item_id), kind=kind, file=file
    )
    return Status(201, next(a for a in records.list_item_attachments(item_id=item_id) if a.id == ref.id))


@items_router.get(
    "/attachments/{int:attachment_id}/download",
    operation_id="downloadAttachment",
    url_name="downloadAttachment",
    response={200: None, **ERRORS},
    openapi_extra={
        "responses": {
            "200": {
                "description": "The file, as uploaded.",
                "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
            }
        }
    },
)
def download_attachment(request: HttpRequest, attachment_id: int) -> FileResponse:
    attachment = records.get_attachment(attachment_id=attachment_id)
    return FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        filename=attachment.original_name,
        content_type=attachment.content_type,
    )


# --- assignment ------------------------------------------------------------------------------------------------


@items_router.post("/items/{int:item_id}/claim", response={200: ItemRowOut, **STUB_ERRORS}, operation_id="claimItem")
def claim_item(request: HttpRequest, item_id: int) -> ItemRowOut:
    """A reviewer takes an item: submitted -> in_review, assigned to them. [workstream E]"""
    raise NotImplementedYet("claiming")


@items_router.post("/items/{int:item_id}/assign", response={200: ItemRowOut, **STUB_ERRORS}, operation_id="assignItem")
def assign_item(request: HttpRequest, item_id: int, body: AssignIn) -> ItemRowOut:
    """Manual assignment by a lead, or a reviewer handing off their own item. [workstream E]"""
    raise NotImplementedYet("assignment")


@items_router.post("/items/bulk/assign", response={200: BulkResultOut, **STUB_ERRORS}, operation_id="bulkAssignItems")
def bulk_assign(request: HttpRequest, body: BulkAssignIn) -> BulkResultOut:
    """[workstream E]"""
    raise NotImplementedYet("bulk assignment")


# --- placements ------------------------------------------------------------------------------------------------


@items_router.get(
    "/items/{int:item_id}/placements", response={200: list[PlacementOut], **ERRORS}, operation_id="listPlacements"
)
def list_placements(request: HttpRequest, item_id: int) -> list[records.PlacementRow]:
    return list(records.list_placements(item_id=item_id, clock=SYSTEM_CLOCK))


@items_router.post(
    "/items/{int:item_id}/placements", response={201: PlacementOut, **STUB_ERRORS}, operation_id="recordPlacement"
)
def record_placement(request: HttpRequest, item_id: int, body: PlacementIn) -> Status[PlacementOut]:
    """The marketer records where approved content runs. [workstream E]"""
    raise NotImplementedYet("recording placements")


@items_router.patch(
    "/placements/{int:placement_id}", response={200: PlacementOut, **STUB_ERRORS}, operation_id="updatePlacement"
)
def update_placement(request: HttpRequest, placement_id: int, body: PlacementUpdateIn) -> PlacementOut:
    """[workstream E]"""
    raise NotImplementedYet("updating placements")


@items_router.post(
    "/placements/{int:placement_id}/confirm-takedown",
    response={200: PlacementOut, **STUB_ERRORS},
    operation_id="confirmTakedown",
)
def confirm_takedown(request: HttpRequest, placement_id: int) -> PlacementOut:
    """Stops the "time to fix live content" clock (ruling 6). [workstream E]"""
    raise NotImplementedYet("confirming takedowns")


# --- saved views -----------------------------------------------------------------------------------------------


@items_router.get("/views", response={200: list[SavedViewOut], **ERRORS}, operation_id="listSavedViews")
def list_saved_views(request: HttpRequest) -> list[records.SavedViewRow]:
    return list(records.list_saved_views(owner=current_user(request)))


@items_router.post("/views", response={201: SavedViewOut, **ERRORS}, operation_id="createSavedView")
def create_saved_view(request: HttpRequest, body: SavedViewIn) -> Status[records.SavedViewRow]:
    viewer = current_user(request)
    view_id = services.create_saved_view(
        actor=viewer,
        data=services.NewSavedView(name=body.name, filters=body.filters, sort=body.sort, columns=tuple(body.columns)),
    )
    return Status(201, next(v for v in records.list_saved_views(owner=viewer) if v.id == view_id))


@items_router.delete("/views/{int:view_id}", response={204: None, **ERRORS}, operation_id="deleteSavedView")
def delete_saved_view(request: HttpRequest, view_id: int) -> Status[None]:
    services.delete_saved_view(actor=current_user(request), view_id=view_id)
    return Status(204, None)


# --- decisions -------------------------------------------------------------------------------------------------


@decisions_router.get(
    "/items/{int:item_id}/decisions", response={200: list[DecisionOut], **ERRORS}, operation_id="listDecisions"
)
def list_decisions(request: HttpRequest, item_id: int) -> list[records.DecisionRow]:
    return list(records.list_decisions(item_id=item_id))


@decisions_router.post(
    "/items/{int:item_id}/decisions", response={201: DecisionOut, **STUB_ERRORS}, operation_id="recordDecision"
)
def record_decision(request: HttpRequest, item_id: int, body: DecisionIn) -> Status[DecisionOut]:
    """Approve, approve with edits, request changes, or reject. Approve needs every finding triaged
    (409 open_findings_block_decision) and the AI check finished (409 ai_check_pending). [workstream E]"""
    raise NotImplementedYet("decisions")


@decisions_router.post(
    "/items/{int:item_id}/reaffirm", response={201: DecisionOut, **STUB_ERRORS}, operation_id="reaffirmApproval"
)
def reaffirm(request: HttpRequest, item_id: int, body: ReaffirmIn) -> Status[DecisionOut]:
    """needs_rereview -> approved on the same version. [workstream E]"""
    raise NotImplementedYet("reaffirming")


@decisions_router.post("/items/{int:item_id}/pull", response={200: ItemRowOut, **STUB_ERRORS}, operation_id="pullItem")
def pull_item(request: HttpRequest, item_id: int, body: PullIn) -> ItemRowOut:
    """Request takedown of live content; the item goes to withdrawn (ruling 6). [workstream E]"""
    raise NotImplementedYet("pulling content")


@decisions_router.post(
    "/items/bulk/fast-track-approve", response={200: BulkResultOut, **STUB_ERRORS}, operation_id="bulkFastTrackApprove"
)
def bulk_fast_track(request: HttpRequest, body: BulkFastTrackIn) -> BulkResultOut:
    """Approve generated terms-change versions; items with open findings are skipped (ruling 4). [workstream F]"""
    raise NotImplementedYet("fast-track approval")


# --- library ---------------------------------------------------------------------------------------------------


@library_router.get("/library", response={200: ItemPageOut, **ERRORS}, operation_id="listLibrary")
def list_library(
    request: HttpRequest,
    filters: Query[ItemFilter],
    sort: ItemSort = ItemSort.UPDATED,
    cursor: str | None = None,
    limit: PageLimit = 50,
) -> selectors.ItemPage:
    """The approved archive, including legacy items. `status` is ignored: always approved."""
    archive = filters.model_copy(update={"status": [ItemStatus.APPROVED]})
    return selectors.list_items(viewer=current_user(request), filters=archive, sort=sort, cursor=cursor, limit=limit)


@library_router.get("/library/search", response={200: SearchResultsOut, **ERRORS}, operation_id="searchLibrary")
def search_library(
    request: HttpRequest,
    filters: Query[ItemFilter],
    query: Annotated[str, Query(min_length=1, max_length=500)],
    mode: Query[search.SearchMode] = search.SearchMode.TEXT,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    """Precedent search. `phrase`: exact wording, case-insensitive. `text`: full-text with web-search syntax
    ("quoted phrases", -exclusions, or)."""
    viewer = current_user(request)
    if mode is search.SearchMode.PHRASE:
        hits = search.find_phrase(viewer=viewer, phrase=query, filters=filters, limit=limit)
    else:
        hits = search.search_text(viewer=viewer, query=query, filters=filters, limit=limit)
    return {"mode": mode.value, "query": query, "hits": hits}
