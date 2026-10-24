from django.http import HttpRequest
from ninja import Router

from core.schemas import HealthOut
from core.selectors import database_is_reachable

router = Router(tags=["core"])


@router.get("/health", response=HealthOut, auth=None, operation_id="health")
def health(request: HttpRequest) -> HealthOut:
    database = database_is_reachable()
    return HealthOut(status="ok" if database else "degraded", database=database)
