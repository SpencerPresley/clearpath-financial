"""Drift monitor and demo-page routers. Thin: parse, call a service or selector, return a schema."""

from django.http import HttpRequest
from ninja import Router, Status

from accounts.api import current_user
from core.domain import DriftTrigger
from core.schemas import ERRORS
from drift import demo, selectors, services, throttles
from drift.schemas import DemoPageOut, DemoPageUpdateIn, ItemDriftOut, SnapshotOut

router = Router(tags=["drift"])
demo_router = Router(tags=["demo"])


@router.get("/items/{int:item_id}/drift", response={200: ItemDriftOut, **ERRORS}, operation_id="getItemDrift")
def item_drift(request: HttpRequest, item_id: int) -> selectors.ItemDrift:
    """The item's placements that have a web address, each with its latest drift check."""
    return selectors.item_drift(item_id=item_id)


@router.post(
    "/placements/{int:placement_id}/drift-checks",
    response={202: SnapshotOut, **ERRORS},
    operation_id="checkPlacementDrift",
    throttle=[throttles.check_now_throttle()],
)
def check_now(request: HttpRequest, placement_id: int) -> Status[selectors.SnapshotView]:
    """Check now: queue a check of the placement's page (the one in flight, if any). Poll `getItemDrift`."""
    snapshot_id = services.request_check(
        actor=current_user(request), placement_id=placement_id, trigger=DriftTrigger.MANUAL
    )
    return Status(202, selectors.get_snapshot(snapshot_id=snapshot_id))


def _demo_out(page: demo.DemoPage) -> DemoPageOut:
    return DemoPageOut(
        slug=page.slug,
        partner=page.partner,
        url=demo.page_url(page.slug),
        edited=demo.is_edited(page.slug),
        edit_summary=page.edit_summary,
        expected=page.expected,
    )


@demo_router.get("/demo/partner-pages", response={200: list[DemoPageOut], **ERRORS}, operation_id="listDemoPages")
def list_demo_pages(request: HttpRequest) -> list[DemoPageOut]:
    """The demo partner pages and whether each shows its edited variant (demo only)."""
    return [_demo_out(page) for page in demo.PAGES]


@demo_router.put("/demo/partner-pages/{slug}", response={200: DemoPageOut, **ERRORS}, operation_id="setDemoPageEdited")
def set_demo_page(request: HttpRequest, slug: str, body: DemoPageUpdateIn) -> DemoPageOut:
    """Lead or admin: "Simulate edit" publishes the page's edited variant; `edited: false` restores it (demo only)."""
    return _demo_out(demo.set_edited(actor=current_user(request), slug=slug, edited=body.edited))
