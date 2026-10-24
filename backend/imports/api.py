from django.http import HttpRequest
from ninja import File, Router, Status, UploadedFile

from accounts.api import current_user
from core.schemas import ERRORS
from imports import selectors, services
from imports.normalize import StatusOverride, ValueOverride
from imports.schemas import (
    ImportCommitIn,
    ImportJobOut,
    ImportJobSummaryOut,
    ImportMappingIn,
    ImportPreviewOut,
)

router = Router(tags=["imports"])


@router.get("/imports", response={200: list[ImportJobSummaryOut], **ERRORS}, operation_id="listImports")
def list_imports(request: HttpRequest) -> list[selectors.ImportJobRow]:
    """The 20 most recent imports. Admins only."""
    return list(selectors.list_imports(viewer=current_user(request)))


@router.post("/imports", response={201: ImportJobOut, **ERRORS}, operation_id="uploadImport")
def upload(request: HttpRequest, file: File[UploadedFile]) -> Status[selectors.ImportJobDetail]:
    """Upload a tracker xlsx; reads it and guesses the column mapping. Admins only. 422 if it isn't an xlsx."""
    actor = current_user(request)
    job_id = services.create_import(actor=actor, filename=file.name or "tracker.xlsx", source=file)
    return Status(201, selectors.get_import(viewer=actor, job_id=job_id))


@router.post("/imports/sample", response={201: ImportJobOut, **ERRORS}, operation_id="loadSampleImport")
def load_sample(request: HttpRequest) -> Status[selectors.ImportJobDetail]:
    """Start an import from the bundled sample tracker ("Load sample tracker")."""
    actor = current_user(request)
    job_id = services.create_sample_import(actor=actor)
    return Status(201, selectors.get_import(viewer=actor, job_id=job_id))


@router.get("/imports/{int:job_id}", response={200: ImportJobOut, **ERRORS}, operation_id="getImport")
def get_import(request: HttpRequest, job_id: int) -> selectors.ImportJobDetail:
    """The job, its columns and current mapping. Poll this after `commitImport`."""
    return selectors.get_import(viewer=current_user(request), job_id=job_id)


@router.put(
    "/imports/{int:job_id}/mapping", response={200: ImportPreviewOut, **ERRORS}, operation_id="setImportMapping"
)
def set_mapping(request: HttpRequest, job_id: int, body: ImportMappingIn) -> selectors.ImportPreview:
    """Save the column, status-value, and value mappings; returns the refreshed preview."""
    actor = current_user(request)
    statuses, values = body.status_values, body.value_mappings
    update = services.MappingUpdate(
        columns={c.source: c.target for c in body.columns},
        statuses=None
        if statuses is None
        else tuple(StatusOverride(s.source_value, s.status, s.outcome) for s in statuses),
        values=None if values is None else tuple(ValueOverride(v.field, v.source_value, v.value) for v in values),
    )
    services.set_mapping(actor=actor, job_id=job_id, update=update)
    return selectors.get_preview(viewer=actor, job_id=job_id)


@router.get(
    "/imports/{int:job_id}/preview", response={200: ImportPreviewOut, **ERRORS}, operation_id="getImportPreview"
)
def preview(request: HttpRequest, job_id: int) -> selectors.ImportPreview:
    """Every row with what commit does with it, and every problem. Row problems are values, not errors."""
    return selectors.get_preview(viewer=current_user(request), job_id=job_id)


@router.post("/imports/{int:job_id}/commit", response={202: ImportJobOut, **ERRORS}, operation_id="commitImport")
def commit(request: HttpRequest, job_id: int, body: ImportCommitIn) -> Status[selectors.ImportJobDetail]:
    """Create the legacy items in the background; poll `getImport`. Safe to repeat: nothing is imported twice."""
    actor = current_user(request)
    services.request_commit(actor=actor, job_id=job_id, skip_blocked=body.skip_rows_with_problems)
    return Status(202, selectors.get_import(viewer=actor, job_id=job_id))
