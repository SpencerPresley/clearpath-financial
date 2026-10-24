"""Span validation for model findings: the invariant that a kept LLM finding's quote sits exactly at its span.

Offsets are Python `str` indices (Unicode code points), half-open `[start, end)`, the same convention as the code
engine. Matching is exact: no case folding, whitespace collapsing, or quote/dash normalization. A model that
"straightens" a curly apostrophe has not quoted the copy.

Models are bad at counting characters, so a quote that occurs exactly once in the text is re-anchored to where it
actually is, and the caller records that. The stored span is still exact, so the invariant holds on what's kept.
"""

from dataclasses import dataclass
from enum import StrEnum

from checks.engine.types import Span


class SpanRejection(StrEnum):
    EMPTY_QUOTE = "empty_quote"
    QUOTE_NOT_FOUND = "quote_not_found"
    AMBIGUOUS_QUOTE = "ambiguous_quote"  # several occurrences and the offsets match none of them


@dataclass(frozen=True)
class Anchor:
    span: Span
    reanchored: bool  # True when the model's offsets were wrong and the unique occurrence was used instead


def _occurrences(text: str, quote: str, limit: int) -> list[int]:
    """Start offsets of `quote` in `text`, overlapping ones included ("aa" occurs twice in "aaa"), up to `limit`."""
    found: list[int] = []
    i = text.find(quote)
    while i != -1 and len(found) < limit:
        found.append(i)
        i = text.find(quote, i + 1)
    return found


def anchor_quote(text: str, quote: str, start: int, end: int) -> Anchor | SpanRejection:
    if not quote:
        return SpanRejection.EMPTY_QUOTE
    if 0 <= start <= end <= len(text) and text[start:end] == quote:
        return Anchor(Span(start, end), reanchored=False)
    found = _occurrences(text, quote, limit=2)
    if not found:
        return SpanRejection.QUOTE_NOT_FOUND
    if len(found) > 1:
        return SpanRejection.AMBIGUOUS_QUOTE
    return Anchor(Span(found[0], found[0] + len(quote)), reanchored=True)
