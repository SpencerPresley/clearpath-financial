from django.http import FileResponse, HttpRequest
from ninja import Router, Status

from accounts.api import current_user
from core.schemas import ERRORS
from exports import evidence, selectors, services
from exports.schemas import EvidencePackOut, ExportIn, ExportOut

router = Router(tags=["exports"])

_CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}


@router.post("/exports", response={202: ExportOut, **ERRORS}, operation_id="createExport")
def create_export(request: HttpRequest, body: ExportIn) -> Status[selectors.ExportJobRow]:
    """Build an xlsx of the filtered view in the background; poll `getExport`. Reviewers, leads, admins."""
    actor = current_user(request)
    export_id = services.request_export(
        actor=actor, filters=body.filters, sort=body.sort, include_evidence_packs=body.include_evidence_packs
    )
    return Status(202, selectors.get_export(viewer=actor, export_id=export_id))


@router.get("/exports/{int:export_id}", response={200: ExportOut, **ERRORS}, operation_id="getExport")
def get_export(request: HttpRequest, export_id: int) -> selectors.ExportJobRow:
    """Status of an export you requested; `download_url` once ready."""
    return selectors.get_export(viewer=current_user(request), export_id=export_id)


@router.get(
    "/exports/{int:export_id}/download",
    operation_id="downloadExport",
    url_name="downloadExport",
    response={200: None, **ERRORS},
    openapi_extra={
        "responses": {
            200: {
                "description": "The xlsx or zip.",
                "content": {
                    _CONTENT_TYPES["xlsx"]: {"schema": {"type": "string", "format": "binary"}},
                    _CONTENT_TYPES["zip"]: {"schema": {"type": "string", "format": "binary"}},
                },
            }
        }
    },
)
def download_export(request: HttpRequest, export_id: int) -> FileResponse:
    """The file. Only its requester (or an admin) can download it; 409 until it's ready."""
    job = selectors.export_for_download(viewer=current_user(request), export_id=export_id)
    suffix = job.filename.rsplit(".", 1)[-1]
    return FileResponse(
        job.file.open("rb"),
        as_attachment=True,
        filename=job.filename,
        content_type=_CONTENT_TYPES.get(suffix, "application/octet-stream"),
    )


@router.get(
    "/items/{int:item_id}/evidence-pack", response={200: EvidencePackOut, **ERRORS}, operation_id="getEvidencePack"
)
def get_evidence_pack(request: HttpRequest, item_id: int) -> evidence.EvidencePack:
    """The latest approval's record. 409 if the item was never approved (or is a legacy import)."""
    current_user(request)
    return evidence.evidence_pack(item_id=item_id)


@router.post(
    "/items/{int:item_id}/evidence-pack", response={202: ExportOut, **ERRORS}, operation_id="createEvidencePack"
)
def create_evidence_pack(request: HttpRequest, item_id: int) -> Status[selectors.ExportJobRow]:
    """Build the evidence pack zip (files, hashes, history) in the background; poll `getExport`."""
    actor = current_user(request)
    export_id = services.request_evidence_pack(actor=actor, item_id=item_id)
    return Status(202, selectors.get_export(viewer=actor, export_id=export_id))
