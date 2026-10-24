import pytest

from checks.contracts import CodeCheckResult, FindingDraft, Span
from core.domain import FindingSource, Severity


def test_span_rejects_inverted_or_negative() -> None:
    with pytest.raises(ValueError, match="0 <= start < end"):
        Span(5, 5)
    with pytest.raises(ValueError, match="0 <= start < end"):
        Span(-1, 3)


def test_span_slices_text() -> None:
    assert Span(6, 15).of("Rates as low as 7.49%") == "as low as"


def test_finding_draft_quote_must_match_span_presence() -> None:
    with pytest.raises(ValueError, match="quote"):
        FindingDraft(
            rule_id="x",
            citation="c",
            source=FindingSource.CODE,
            severity=Severity.WARNING,
            message="m",
            span=Span(0, 1),
        )


def test_empty_result_is_valid() -> None:
    assert CodeCheckResult.empty().findings == ()
