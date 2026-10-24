from django.http import HttpRequest
from ninja import Router, Status

from core.errors import NotImplementedYet
from core.schemas import STUB_ERRORS
from exports.schemas import EvidencePackOut, ExportIn, ExportOut

router = Router(tags=["exports"])


@router.post("/exports", response={202: ExportOut, **STUB_ERRORS}, operation_id="createExport")
def create_export(request: HttpRequest, body: ExportIn) -> Status[ExportOut]:
    """Build an xlsx of the filtered items in the background; poll `getExport`. [workstream G]"""
    raise NotImplementedYet("export")


@router.get("/exports/{int:export_id}", response={200: ExportOut, **STUB_ERRORS}, operation_id="getExport")
def get_export(request: HttpRequest, export_id: int) -> ExportOut:
    """[workstream G]"""
    raise NotImplementedYet("export")


@router.get(
    "/items/{int:item_id}/evidence-pack", response={200: EvidencePackOut, **STUB_ERRORS}, operation_id="getEvidencePack"
)
def evidence_pack(request: HttpRequest, item_id: int) -> EvidencePackOut:
    """The latest approval's record. 409 if the item was never approved. [workstream G]"""
    raise NotImplementedYet("evidence packs")
