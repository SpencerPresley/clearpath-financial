"""Live model smoke tests. Deselected by default (`addopts = -m "not live"`). Run with:

    ANTHROPIC_API_KEY=... uv run pytest -m live checks/llm

These check the wiring against the real API: the request is accepted (no temperature, forced tool choice),
the output parses, and caching engages on a repeat call. They don't check quality; the eval measures that.
"""

import os

import pytest

from checks.engine import run_code_checks
from checks.llm import get_review_model, review_copy
from checks.llm.eval.__main__ import demo_terms
from checks.llm.eval.corpus import CASES
from checks.llm.eval.runner import context_for

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY"),
]


def test_live_haiku_returns_valid_output_and_caches():
    case = next(c for c in CASES if c.name == "affiliate_injection")
    ctx = context_for(case, demo_terms)
    code = run_code_checks(ctx).findings
    model = get_review_model()
    first = review_copy(ctx, code_findings=code, model=model)
    second = review_copy(ctx, code_findings=code, model=model)
    assert first.output_valid
    assert second.output_valid
    assert first.usage.input_tokens > 0
    assert first.usage.cache_creation_tokens + first.usage.cache_read_tokens > 0
    assert second.usage.cache_read_tokens > 0
    assert run_code_checks(ctx).findings == code
