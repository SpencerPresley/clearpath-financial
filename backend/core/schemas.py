from typing import Final, Literal

from ninja import Schema
from pydantic import Field, JsonValue


class HealthOut(Schema):
    status: Literal["ok", "degraded"]
    database: bool


class FieldErrorOut(Schema):
    loc: list[str | int]
    message: str
    type: str


class ErrorOut(Schema):
    """Every non-2xx response body. `code` is stable; switch on it, not on `message`."""

    code: str = Field(examples=["open_findings_block_decision"])
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)
    fields: list[FieldErrorOut] = Field(default_factory=list)


# Response-dict fragments: `response={200: ItemDetailOut, **ERRORS}`. Stubs use STUB_ERRORS (adds 501).
ERRORS: Final[dict[frozenset[int], type[ErrorOut]]] = {frozenset({400, 401, 403, 404, 409, 422}): ErrorOut}
STUB_ERRORS: Final[dict[frozenset[int], type[ErrorOut]]] = {frozenset({400, 401, 403, 404, 409, 422, 501}): ErrorOut}
