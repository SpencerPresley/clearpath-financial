from django.http import HttpRequest
from ninja import File, Router, Status, UploadedFile

from core.errors import NotImplementedYet
from core.schemas import STUB_ERRORS
from imports.schemas import ImportCommitIn, ImportCommitOut, ImportJobOut, ImportMappingIn, ImportPreviewOut

router = Router(tags=["imports"])


@router.post("/imports", response={201: ImportJobOut, **STUB_ERRORS}, operation_id="uploadImport")
def upload(request: HttpRequest, file: File[UploadedFile]) -> Status[ImportJobOut]:
    """Upload a tracker xlsx; detects columns and suggests a mapping. Admins only. [workstream G]"""
    raise NotImplementedYet("import")


@router.post("/imports/sample", response={201: ImportJobOut, **STUB_ERRORS}, operation_id="loadSampleImport")
def load_sample(request: HttpRequest) -> Status[ImportJobOut]:
    """Start an import from the bundled sample tracker. [workstream G]"""
    raise NotImplementedYet("import")


@router.get("/imports/{int:job_id}", response={200: ImportJobOut, **STUB_ERRORS}, operation_id="getImport")
def get_import(request: HttpRequest, job_id: int) -> ImportJobOut:
    """[workstream G]"""
    raise NotImplementedYet("import")


@router.put(
    "/imports/{int:job_id}/mapping", response={200: ImportPreviewOut, **STUB_ERRORS}, operation_id="setImportMapping"
)
def set_mapping(request: HttpRequest, job_id: int, body: ImportMappingIn) -> ImportPreviewOut:
    """Save the column and status-value mapping; returns the refreshed preview. [workstream G]"""
    raise NotImplementedYet("import")


@router.get(
    "/imports/{int:job_id}/preview", response={200: ImportPreviewOut, **STUB_ERRORS}, operation_id="getImportPreview"
)
def preview(request: HttpRequest, job_id: int) -> ImportPreviewOut:
    """Row problems are reported values, not errors (spec §6.1). [workstream G]"""
    raise NotImplementedYet("import")


@router.post(
    "/imports/{int:job_id}/commit", response={200: ImportCommitOut, **STUB_ERRORS}, operation_id="commitImport"
)
def commit(request: HttpRequest, job_id: int, body: ImportCommitIn) -> ImportCommitOut:
    """Create legacy items (is_legacy, legacy_ref kept). [workstream G]"""
    raise NotImplementedYet("import")
