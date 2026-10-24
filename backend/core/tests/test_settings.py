import os

import pytest
from django.db import connection


@pytest.mark.django_db
def test_test_database_name_carries_worktree_suffix() -> None:
    suffix = os.environ.get("CLEARPATH_TEST_DB_SUFFIX", "")
    if not suffix:
        pytest.skip("CLEARPATH_TEST_DB_SUFFIX not set")

    assert connection.settings_dict["NAME"].endswith(f"_{suffix}")
