"""The API contract the frontend generates its client from (spec §8.2: changes go through `make schema`)."""

from typing import Any

import pytest
from django.test import Client

from accounts.models import User
from config.api import api

TAGS = {
    "core",
    "items",
    "findings",
    "decisions",
    "terms",
    "partners",
    "library",
    "imports",
    "exports",
    "metrics",
    "notifications",
    "assistant",
    "admin",
    "me",
}


def _operations() -> list[tuple[str, str, dict[str, Any]]]:
    schema = api.get_openapi_schema()
    return [(path, method, op) for path, ops in schema["paths"].items() for method, op in ops.items()]


def test_schema_exports_as_sorted_json() -> None:
    # `make schema` exports with --sorted; mixed int/str keys (e.g. a "200" in openapi_extra) break it.
    import json

    from django.core.serializers.json import DjangoJSONEncoder

    assert json.dumps(api.get_openapi_schema(), sort_keys=True, cls=DjangoJSONEncoder)


def test_every_operation_has_an_id_and_one_known_tag() -> None:
    for path, method, op in _operations():
        assert op.get("operationId"), (method, path)
        assert len(op.get("tags", [])) == 1, (method, path)
        assert op["tags"][0] in TAGS, (method, path, op["tags"])


def test_operation_ids_are_unique_and_camel_case() -> None:
    ids = [op["operationId"] for _, _, op in _operations()]

    assert len(ids) == len(set(ids))
    assert all(i[0].islower() and "_" not in i for i in ids), ids


def test_every_area_has_operations() -> None:
    tags = {op["tags"][0] for _, _, op in _operations()}

    assert tags == TAGS


def test_error_envelope_is_a_component() -> None:
    components = api.get_openapi_schema()["components"]["schemas"]

    assert {"ErrorOut", "FieldErrorOut"} <= set(components)
    assert "ItemSubmittedEventOut" in components  # typed history entries


def test_schema_component_names_say_what_they_are() -> None:
    schemas = api.get_openapi_schema()["components"]["schemas"]
    enums = {name for name, schema in schemas.items() if "enum" in schema}
    domain_models = {"PersonalLoanTerms", "CreditCardTerms", "FieldChange", "ItemFilter", "JsonValue"}
    domain_models |= {name for name in schemas if name.endswith("Payload")}

    unclear = {n for n in set(schemas) - enums - domain_models if not n.endswith(("In", "Out", "Query"))}

    assert unclear == set()


STUBS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("post", "/api/items/fetch-url", {"url": "https://example.com"}),
    ("post", "/api/items/{item}/versions", {"content_text": "v2"}),
    ("post", "/api/items/{item}/claim", None),
    ("post", "/api/items/{item}/assign", {"assignee_id": None}),
    ("post", "/api/items/bulk/assign", {"item_ids": [1], "assignee_id": None}),
    ("post", "/api/items/{item}/new-round", {}),
    ("post", "/api/items/{item}/placements", {"location": "Blog", "first_run": "2026-11-01"}),
    ("patch", "/api/placements/1", {"monitored": True}),
    ("post", "/api/placements/1/confirm-takedown", None),
    ("post", "/api/findings/1/accept", {}),
    ("post", "/api/findings/1/dismiss", {"reason": "Footer has it"}),
    ("post", "/api/findings/1/reopen", None),
    (
        "post",
        "/api/checks/preview",
        {"content_text": "x", "product": "personal_loan", "channel": "email", "markets": ["CA"]},
    ),
    ("post", "/api/items/{item}/llm-check/retry", None),
    ("post", "/api/items/{item}/decisions", {"outcome": "rejected", "version_n": 1, "reason": "No"}),
    ("post", "/api/items/{item}/reaffirm", {"reason": "Still accurate"}),
    ("post", "/api/items/{item}/pull", {"reason": "Rates changed"}),
    ("post", "/api/items/bulk/fast-track-approve", {"item_ids": [1], "reason": "Numbers only"}),
    ("post", "/api/terms/impact-preview", None),
    ("post", "/api/terms", None),
    ("post", "/api/exports", {"filters": {}}),
    ("get", "/api/exports/1", None),
    ("get", "/api/items/{item}/evidence-pack", None),
    ("post", "/api/imports/sample", None),
    ("get", "/api/imports/1", None),
    ("put", "/api/imports/1/mapping", {"columns": [{"source": "Request ID", "target": "legacy_ref"}]}),
    ("get", "/api/imports/1/preview", None),
    ("post", "/api/imports/1/commit", {}),
    ("get", "/api/metrics/summary", None),
    ("get", "/api/metrics/series?metric=rounds_per_item", None),
    ("post", "/api/assistant/threads", None),
    ("get", "/api/assistant/threads/t1", None),
    ("post", "/api/assistant/threads/t1/messages", {"content": "What's waiting on me?"}),
    ("post", "/api/assistant/threads/t1/approvals/i1", {"decision": "reject"}),
    (
        "post",
        "/api/admin/users",
        {"email": "new@clearpath.demo", "display_name": "New", "roles": ["reviewer"], "password": "x" * 12},
    ),
    ("patch", "/api/admin/users/1", {"is_active": False}),
    ("post", "/api/admin/demo/reset", None),
]

PL_VALUES = {
    "product": "personal_loan",
    "apr_min": "7.49",
    "apr_max": "35.99",
    "amount_min": "1000",
    "amount_max": "50000",
    "term_months": [36],
    "origination_fee_min_pct": "0",
    "origination_fee_max_pct": "8",
}


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "path", "body"), STUBS, ids=[f"{m} {p}" for m, p, _ in STUBS])
def test_stub_endpoints_validate_then_return_501(
    marketer: User, method: str, path: str, body: dict[str, Any] | None
) -> None:
    from reviews.tests.factories import make_item

    client = Client()
    client.force_login(marketer)
    if path.startswith("/api/terms"):
        body = {"product": "personal_loan", "values": PL_VALUES}
    url = path.replace("{item}", str(make_item(marketer).pk))

    response = (
        getattr(client, method)(url, body, content_type="application/json")
        if body is not None
        else getattr(client, method)(url)
    )

    assert response.status_code == 501, response.content
    assert response.json()["code"] == "not_implemented"


@pytest.mark.django_db
def test_stub_still_validates_input_first(marketer: User) -> None:
    client = Client()
    client.force_login(marketer)

    response = client.post("/api/findings/1/dismiss", {"reason": ""}, content_type="application/json")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.django_db
def test_upload_import_stub_accepts_a_file(admin_user: User) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    client = Client()
    client.force_login(admin_user)

    response = client.post("/api/imports", {"file": SimpleUploadedFile("tracker.xlsx", b"PK...")})

    assert response.status_code == 501


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/me", "/api/items", "/api/partners", "/api/notifications"])
def test_operations_require_a_session(path: str) -> None:
    response = Client().get(path)

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
