from .base import *

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
# Never call the model provider from unit tests, even with a key in the environment: AI checks get their model
# through the `checks.tasks.model_factory` seam. The live smoke test reads the key from `env` itself.
ANTHROPIC_API_KEY = None
ANTHROPIC_MODEL = "claude-haiku-5-5"  # pinned: tests assert on the ruleset key, which includes it
# CI runs without Redis; tests that need the Redis cache override this.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# One test database per worktree (CLEARPATH_TEST_DB_SUFFIX=ws0 -> test_clearpath_ws0) so concurrent pytest
# runs against the shared compose Postgres never drop each other's database.
_test_db_name = f"test_{DATABASES['default']['NAME']}"
if env.clearpath_test_db_suffix:
    _test_db_name = f"{_test_db_name}_{env.clearpath_test_db_suffix}"
DATABASES["default"]["TEST"] = {"NAME": _test_db_name}
