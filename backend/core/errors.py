"""Typed domain errors (spec §6.1).

Services raise these; `config.api.install_error_handlers` maps them to HTTP once, as
`{code, message, details, fields}`. Endpoints never catch them. Each class has a stable `code` the frontend
can switch on; messages say what happened and what to do, in one line (spec §5.4).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar

from pydantic import JsonValue

from core.domain import ItemStatus


@dataclass(frozen=True)
class FieldIssue:
    """A problem with one input field; `loc` follows ninja's convention, e.g. ("body", "partner_id")."""

    loc: tuple[str | int, ...]
    message: str
    type: str = "invalid"


class DomainError(Exception):
    code: ClassVar[str] = "domain_error"
    status: ClassVar[int] = 400

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, JsonValue] | None = None,
        fields: Sequence[FieldIssue] = (),
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, JsonValue] = dict(details or {})
        self.fields: tuple[FieldIssue, ...] = tuple(fields)


class InvalidInput(DomainError):
    """Schema-valid input that breaks a business rule (e.g. affiliate page without a partner)."""

    code = "invalid_input"
    status = 422

    @classmethod
    def for_field(cls, field: str, message: str) -> InvalidInput:
        return cls(message, fields=[FieldIssue(loc=("body", field), message=message)])


class NotPermitted(DomainError):
    code = "not_permitted"
    status = 403


class NotFound(DomainError):
    code = "not_found"
    status = 404

    @classmethod
    def entity(cls, entity: str, entity_id: int | str) -> NotFound:
        return cls(f"{entity.capitalize()} {entity_id} doesn't exist.", details={"entity": entity, "id": entity_id})


class Conflict(DomainError):
    """The request is valid but the current state doesn't allow it."""

    code = "conflict"
    status = 409


class InvalidTransition(Conflict):
    code = "invalid_transition"

    def __init__(self, *, action: str, from_status: ItemStatus) -> None:
        super().__init__(
            f"Can't {action.replace('_', ' ')} an item that is {from_status.replace('_', ' ')}.",
            details={"action": action, "from_status": str(from_status)},
        )


class OpenFindingsBlockDecision(Conflict):
    code = "open_findings_block_decision"

    def __init__(self, *, open_count: int) -> None:
        noun = "finding is" if open_count == 1 else "findings are"
        super().__init__(
            f"{open_count} {noun} still open. Accept or dismiss each one first.",
            details={"open_count": open_count},
        )


class AiCheckPending(Conflict):
    code = "ai_check_pending"

    def __init__(self) -> None:
        super().__init__("The AI check is still running. Approve once it finishes.")


class TermsRangeOverlap(Conflict):
    code = "terms_range_overlap"


class NotImplementedYet(DomainError):
    """Raised by contract stubs: the endpoint's shape is final, its behavior lands with another workstream."""

    code = "not_implemented"
    status = 501

    def __init__(self, feature: str) -> None:
        super().__init__(f"{feature.capitalize()} isn't available yet.", details={"feature": feature})
