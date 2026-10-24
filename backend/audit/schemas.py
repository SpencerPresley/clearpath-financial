"""History entries for the API: one schema per EventType, discriminated on `type`, each carrying that type's
typed payload. The frontend's History tab switches on `type` and gets the right payload fields."""

from datetime import datetime
from typing import Annotated, Literal, Union

from ninja import Schema
from pydantic import Field, create_model

from audit.payloads import PAYLOADS
from core.domain import EntityType, ItemStatus
from reviews.schemas import PartyRefOut


class HistoryEntryBase(Schema):
    id: int
    at: datetime
    actor: PartyRefOut | None = Field(description="Null for system actions (sweeps, fan-out).")
    entity: EntityType
    entity_id: int
    from_status: ItemStatus | None
    to_status: ItemStatus | None


def _entry_schema(event_type: str, payload: type) -> type[HistoryEntryBase]:
    name = payload.__name__.removesuffix("Payload") + "EventOut"
    return create_model(
        name,
        __base__=HistoryEntryBase,
        type=(Literal[event_type], ...),  # pyrefly: ignore[not-a-type]  # built per EventType
        payload=(payload, ...),
    )


_ENTRY_SCHEMAS = tuple(_entry_schema(t.value, p) for t, p in PAYLOADS.items())

HistoryEntryOut = Annotated[Union[_ENTRY_SCHEMAS], Field(discriminator="type")]  # noqa: UP007  # pyrefly: ignore[not-a-type]


class ItemHistoryOut(Schema):
    entries: list[HistoryEntryOut]  # pyrefly: ignore[invalid-annotation]
