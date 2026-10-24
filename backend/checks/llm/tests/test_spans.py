"""The span invariant: an LLM finding is kept only if its quote sits exactly at [start, end) in the text.

Offsets are Python str indices (Unicode code points), half-open. A JS client indexes UTF-16 code units, so an
emoji is length 1 here and 2 there; the frontend converts before highlighting.
"""

import pytest

from checks.engine.types import Span
from checks.llm.spans import Anchor, SpanRejection, anchor_quote

TEXT = "Rates as low as 5.99% APR. Apply now. Apply now."


def test_exact_match():
    start = TEXT.index("as low as")
    assert anchor_quote(TEXT, "as low as", start, start + 9) == Anchor(Span(start, start + 9), reanchored=False)


def test_repeated_quote_with_correct_offsets_is_exact():
    second = TEXT.rindex("Apply now")
    assert anchor_quote(TEXT, "Apply now", second, second + 9) == Anchor(Span(second, second + 9), reanchored=False)


def test_reanchors_unique_quote_with_wrong_offsets():
    start = TEXT.index("5.99% APR")
    assert anchor_quote(TEXT, "5.99% APR", 0, 9) == Anchor(Span(start, start + 9), reanchored=True)


@pytest.mark.parametrize(
    ("start", "end"),
    [(-5, 4), (3, 1), (40, 400), (1000, 1009), (0, 0)],
    ids=["negative", "inverted", "past-end", "far-past-end", "empty-range"],
)
def test_reanchors_when_offsets_out_of_bounds_or_negative_or_inverted(start, end):
    real = TEXT.index("as low as")
    assert anchor_quote(TEXT, "as low as", start, end) == Anchor(Span(real, real + 9), reanchored=True)


def test_absent_quote_dropped():
    assert anchor_quote(TEXT, "guaranteed approval", 0, 19) is SpanRejection.QUOTE_NOT_FOUND


def test_ambiguous_quote_dropped():
    assert anchor_quote(TEXT, "Apply now", 0, 9) is SpanRejection.AMBIGUOUS_QUOTE


def test_overlapping_occurrences_are_ambiguous():
    assert anchor_quote("aaa", "aa", 2, 4) is SpanRejection.AMBIGUOUS_QUOTE


def test_overlapping_occurrence_with_correct_offsets_is_exact():
    assert anchor_quote("aaa", "aa", 1, 3) == Anchor(Span(1, 3), reanchored=False)


def test_empty_quote_dropped():
    assert anchor_quote(TEXT, "", 0, 0) is SpanRejection.EMPTY_QUOTE


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        (
            "Rates won\N{RIGHT SINGLE QUOTATION MARK}t affect your score",
            "won't affect",
        ),  # curly apostrophe in copy, straight in quote
        ("Borrow up to\N{NO-BREAK SPACE}$50,000", "up to $50,000"),  # NBSP in copy, space in quote
        ("APRs 7.49%\N{EN DASH}35.99%", "7.49%-35.99%"),  # en dash in copy, hyphen in quote
    ],
    ids=["apostrophe", "nbsp", "dash"],
)
def test_normalized_quote_is_not_found(text, quote):
    assert anchor_quote(text, quote, 0, len(quote)) is SpanRejection.QUOTE_NOT_FOUND


def test_offsets_are_code_points():
    text = "\U0001f4b8 Free money! \U0001f4b8"
    start = 2  # the emoji is one code point (two UTF-16 units in JS)
    assert text[start : start + 10] == "Free money"
    assert anchor_quote(text, "Free money", start, start + 10) == Anchor(Span(2, 12), reanchored=False)
    # A model counting UTF-16 units would say 3..13; the quote is unique so it re-anchors to the code-point span.
    assert anchor_quote(text, "Free money", 3, 13) == Anchor(Span(2, 12), reanchored=True)


def test_emoji_itself_is_quotable():
    text = "Cash fast \U0001f680 apply"
    assert anchor_quote(text, "\U0001f680", 10, 11) == Anchor(Span(10, 11), reanchored=False)


def test_combining_characters_are_separate_code_points():
    text = "Se habla espan\N{COMBINING TILDE}ol"  # n + combining tilde, not the precomposed letter
    assert anchor_quote(text, "espa\N{LATIN SMALL LETTER N WITH TILDE}ol", 9, 16) is SpanRejection.QUOTE_NOT_FOUND
    assert anchor_quote(text, "espan\N{COMBINING TILDE}ol", 9, 17) == Anchor(Span(9, 17), reanchored=False)


def test_case_sensitive():
    assert anchor_quote(TEXT, "AS LOW AS", 6, 15) is SpanRejection.QUOTE_NOT_FOUND


def test_whitespace_is_significant():
    assert anchor_quote(TEXT, "as low as ", 6, 16) == Anchor(Span(6, 16), reanchored=False)
    assert anchor_quote(TEXT, " as low as", 5, 15) == Anchor(Span(5, 15), reanchored=False)
    assert anchor_quote(TEXT, "as  low as", 6, 16) is SpanRejection.QUOTE_NOT_FOUND


def test_whole_text_quote():
    assert anchor_quote("Apply", "Apply", 0, 5) == Anchor(Span(0, 5), reanchored=False)
