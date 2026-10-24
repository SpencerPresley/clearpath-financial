from django.http import HttpRequest
from ninja import Router, Status

from accounts.api import current_user
from checks import prereview, services
from checks.engine import FindingDraft, TermsRefDraft
from checks.schemas import (
    CheckPreviewIn,
    CheckPreviewOut,
    FindingAcceptIn,
    FindingDismissIn,
    FindingDraftOut,
    FindingOut,
    TermsRefDraftOut,
)
from checks.selectors import FindingRow, get_finding, list_findings
from core.domain import TermsField
from core.schemas import ERRORS
from reviews.schemas import ItemRowOut, SpanOut
from reviews.selectors import ItemRow, get_item_row

router = Router(tags=["findings"])


@router.get("/items/{int:item_id}/findings", response={200: list[FindingOut], **ERRORS}, operation_id="listFindings")
def findings(request: HttpRequest, item_id: int, version_n: int | None = None) -> list[FindingRow]:
    """Findings on the current version, or on `version_n`."""
    return list(list_findings(item_id=item_id, version_n=version_n))


@router.post("/findings/{int:finding_id}/accept", response={200: FindingOut, **ERRORS}, operation_id="acceptFinding")
def accept(request: HttpRequest, finding_id: int, body: FindingAcceptIn) -> FindingRow:
    """The problem is real: it becomes a required change. Assignee or lead; current version only."""
    services.accept_finding(actor=current_user(request), finding_id=finding_id, note=body.note)
    return get_finding(finding_id=finding_id)


@router.post("/findings/{int:finding_id}/dismiss", response={200: FindingOut, **ERRORS}, operation_id="dismissFinding")
def dismiss(request: HttpRequest, finding_id: int, body: FindingDismissIn) -> FindingRow:
    """Not a problem here, with the reason. Assignee or lead; current version only."""
    services.dismiss_finding(actor=current_user(request), finding_id=finding_id, reason=body.reason)
    return get_finding(finding_id=finding_id)


@router.post("/findings/{int:finding_id}/reopen", response={200: FindingOut, **ERRORS}, operation_id="reopenFinding")
def reopen(request: HttpRequest, finding_id: int) -> FindingRow:
    services.reopen_finding(actor=current_user(request), finding_id=finding_id)
    return get_finding(finding_id=finding_id)


def _finding_out(f: FindingDraft) -> FindingDraftOut:
    return FindingDraftOut(
        rule_id=f.rule_id,
        citation=f.citation,
        source=f.source,
        severity=f.severity,
        message=f.message,
        suggested_fix=f.suggested_fix or "",
        fix_kind=f.fix_kind,
        replacement_text=f.replacement_text,
        span=SpanOut(start=f.span.start, end=f.span.end) if f.span is not None else None,
        quote=f.quote,
    )


def _ref_out(ref: TermsRefDraft, text: str) -> TermsRefDraftOut:
    return TermsRefDraftOut(
        field=TermsField(ref.field),
        span=SpanOut(start=ref.span.start, end=ref.span.end),
        quote=text[ref.span.start : ref.span.end],
        value=str(ref.quoted_value.normalize()),
    )


@router.post("/checks/preview", response={200: CheckPreviewOut, **ERRORS}, operation_id="previewChecks")
def preview(request: HttpRequest, body: CheckPreviewIn) -> CheckPreviewOut:
    """Run the code rules on unsaved text, as the marketer types; nothing is stored."""
    result = services.preview_checks(
        data=services.PreviewInput(
            content_text=body.content_text,
            product=body.product,
            channel=body.channel,
            markets=tuple(body.markets),
            partner_id=body.partner_id,
            attachment_kinds=tuple(body.attachment_kinds),
        )
    )
    return CheckPreviewOut(
        findings=[_finding_out(f) for f in result.findings],
        terms_refs=[_ref_out(r, body.content_text) for r in result.terms_refs],
        ruleset_key=result.ruleset_key,
    )


@router.post("/items/{int:item_id}/llm-check/retry", response={202: ItemRowOut, **ERRORS}, operation_id="retryLlmCheck")
def retry_llm_check(request: HttpRequest, item_id: int) -> Status[ItemRow]:
    """Run a failed AI check again on the current version (reviewer or lead, while the item is under review).
    It starts as `pending`; poll the item for the result."""
    prereview.retry_check(actor=current_user(request), item_id=item_id)
    return Status(202, get_item_row(item_id=item_id))
