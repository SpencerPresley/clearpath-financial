import pytest
from django.test import Client


@pytest.mark.django_db
def test_health_reports_ok_when_database_is_reachable(client: Client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True}


@pytest.mark.django_db
def test_health_needs_no_session(client: Client) -> None:
    client.logout()

    response = client.get("/api/health")

    assert response.status_code == 200


@pytest.mark.django_db
def test_required_postgres_extensions_are_installed() -> None:
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension")
        installed = {row[0] for row in cursor.fetchall()}

    assert {"btree_gist", "pg_trgm"} <= installed
