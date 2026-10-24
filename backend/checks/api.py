from django.http import HttpRequest
from ninja import Router

from checks.schemas import CheckPreviewIn, CheckPreviewOut, FindingAcceptIn, FindingDismissIn, FindingOut
from checks.selectors import FindingRow, list_findings
from core.errors import NotImplementedYet
from core.schemas import ERRORS, STUB_ERRORS
from reviews.schemas import ItemRowOut

router = Router(tags=["findings"])


@router.get("/items/{int:item_id}/findings", response={200: list[FindingOut], **ERRORS}, operation_id="listFindings")
def findings(request: HttpRequest, item_id: int, version_n: int | None = None) -> list[FindingRow]:
    """Findings on the current version, or on `version_n`."""
    return list(list_findings(item_id=item_id, version_n=version_n))


@router.post(
    "/findings/{int:finding_id}/accept", response={200: FindingOut, **STUB_ERRORS}, operation_id="acceptFinding"
)
def accept(request: HttpRequest, finding_id: int, body: FindingAcceptIn) -> FindingOut:
    """Accepted findings become required changes in the request-changes message. [workstream E]"""
    raise NotImplementedYet("accepting findings")


@router.post(
    "/findings/{int:finding_id}/dismiss", response={200: FindingOut, **STUB_ERRORS}, operation_id="dismissFinding"
)
def dismiss(request: HttpRequest, finding_id: int, body: FindingDismissIn) -> FindingOut:
    """[workstream E]"""
    raise NotImplementedYet("dismissing findings")


@router.post(
    "/findings/{int:finding_id}/reopen", response={200: FindingOut, **STUB_ERRORS}, operation_id="reopenFinding"
)
def reopen(request: HttpRequest, finding_id: int) -> FindingOut:
    """[workstream E]"""
    raise NotImplementedYet("reopening findings")


@router.post("/checks/preview", response={200: CheckPreviewOut, **STUB_ERRORS}, operation_id="previewChecks")
def preview(request: HttpRequest, body: CheckPreviewIn) -> CheckPreviewOut:
    """Run the code rules on unsaved text; nothing is stored. [workstream C]"""
    raise NotImplementedYet("live checks")


@router.post(
    "/items/{int:item_id}/llm-check/retry", response={202: ItemRowOut, **STUB_ERRORS}, operation_id="retryLlmCheck"
)
def retry_llm_check(request: HttpRequest, item_id: int) -> ItemRowOut:
    """Re-run a failed AI check on the current version. [workstream D]"""
    raise NotImplementedYet("retrying the AI check")
