"""The API contract the frontend generates its client from (spec §8.2: changes go through `make schema`)."""

import typing
from typing import Any

import pytest
from django.core.management import get_commands, load_command_class
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
    "users",
    "me",
    "drift",
    "demo",
}


def _operations() -> list[tuple[str, str, dict[str, Any]]]:
    schema = api.get_openapi_schema()
    return [(path, method, op) for path, ops in schema["paths"].items() for method, op in ops.items()]


def test_schema_export_needs_no_database() -> None:
    # The api-contract drift job has no Postgres; GeneratedField's system check opens a connection, so the export
    # command must skip system checks (backend CI runs them, with a database).
    app = get_commands()["export_openapi_schema"]
    command = load_command_class(app, "export_openapi_schema")

    assert (app, command.requires_system_checks) == ("core", [])


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
    domain_models = {"PersonalLoanTerms", "CreditCardTerms", "FieldChange", "LegacyTimeline", "ItemFilter", "JsonValue"}
    domain_models |= {name for name in schemas if name.endswith("Payload")}

    unclear = {n for n in set(schemas) - enums - domain_models if not n.endswith(("In", "Out", "Query"))}

    assert unclear == set()


def test_no_operation_returns_a_raw_dict() -> None:
    # Backend CLAUDE.md: typed dataclasses or schemas across boundaries, never raw dicts.
    offenders = []
    for router in api._get_bound_routers():
        for path_view in router.path_operations.values():
            for operation in path_view.operations:
                returns = typing.get_type_hints(operation.view_func).get("return")
                if returns is dict or typing.get_origin(returns) is dict:
                    offenders.append(operation.operation_id)

    assert offenders == []


def test_no_operation_is_a_stub() -> None:
    """Every contract stub has landed: no operation documents a 501 any more."""
    paths = api.get_openapi_schema()["paths"]
    stubs = [op["operationId"] for ops in paths.values() for op in ops.values() if "501" in op.get("responses", {})]

    assert stubs == []


@pytest.mark.django_db
def test_input_is_validated_before_permissions(marketer: User) -> None:
    client = Client()
    client.force_login(marketer)

    response = client.post("/api/admin/users", {"email": "new@clearpath.demo"}, content_type="application/json")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/me", "/api/items", "/api/partners", "/api/notifications"])
def test_operations_require_a_session(path: str) -> None:
    response = Client().get(path)

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
