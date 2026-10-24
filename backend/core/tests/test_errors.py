"""The error envelope: every failure the API returns has {code, message, details, fields}."""

import pytest
from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.testing import TestClient

from config.api import install_error_handlers
from core.domain import ItemStatus
from core.errors import (
    DomainError,
    InvalidInput,
    InvalidTransition,
    NotFound,
    NotImplementedYet,
    OpenFindingsBlockDecision,
)


class _Body(Schema):
    count: int


def _client() -> TestClient:
    api = NinjaAPI(urls_namespace="errors-test")
    install_error_handlers(api)

    @api.post("/blocked")
    def blocked(request: HttpRequest) -> None:
        raise OpenFindingsBlockDecision(open_count=2)

    @api.post("/transition")
    def transition(request: HttpRequest) -> None:
        raise InvalidTransition(action="approve", from_status=ItemStatus.DRAFT)

    @api.post("/invalid")
    def invalid(request: HttpRequest) -> None:
        raise InvalidInput.for_field("partner_id", "A partner is required for affiliate pages.")

    @api.post("/stub")
    def stub(request: HttpRequest) -> None:
        raise NotImplementedYet("decisions")

    @api.post("/validated")
    def validated(request: HttpRequest, body: _Body) -> None:
        return None

    return TestClient(api)


def test_domain_error_maps_to_status_and_envelope() -> None:
    response = _client().post("/blocked")

    assert response.status_code == 409
    assert response.json() == {
        "code": "open_findings_block_decision",
        "message": "2 findings are still open. Accept or dismiss each one first.",
        "details": {"open_count": 2},
        "fields": [],
    }


def test_invalid_transition_names_action_and_state() -> None:
    response = _client().post("/transition")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "invalid_transition"
    assert body["details"] == {"action": "approve", "from_status": "draft"}


def test_invalid_input_points_at_the_field() -> None:
    response = _client().post("/invalid")

    assert response.status_code == 422
    assert response.json()["fields"] == [
        {"loc": ["body", "partner_id"], "message": "A partner is required for affiliate pages.", "type": "invalid"}
    ]


def test_not_implemented_is_501() -> None:
    response = _client().post("/stub")

    assert response.status_code == 501
    assert response.json()["code"] == "not_implemented"
    assert response.json()["details"] == {"feature": "decisions"}


def test_schema_validation_error_uses_the_envelope() -> None:
    response = _client().post("/validated", json={"count": "many"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["fields"][0]["loc"] == ["body", "body", "count"]


def test_every_domain_error_has_a_distinct_code() -> None:
    def walk(cls: type[DomainError]) -> list[type[DomainError]]:
        return [cls, *(c for sub in cls.__subclasses__() for c in walk(sub))]

    classes = walk(DomainError)
    codes = [c.code for c in classes]

    assert len(codes) == len(set(codes)), codes
    assert NotFound.status == 404


@pytest.mark.parametrize("status", [400, 403, 404, 409, 422, 501])
def test_error_statuses_are_declared(status: int) -> None:
    from core.schemas import STUB_ERRORS

    assert any(status in codes for codes in STUB_ERRORS)
