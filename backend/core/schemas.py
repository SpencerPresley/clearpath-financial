from typing import Literal

from ninja import Schema


class HealthOut(Schema):
    status: Literal["ok", "degraded"]
    database: bool
