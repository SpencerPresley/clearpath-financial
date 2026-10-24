"""Regex vocabulary and text-window helpers.

The text is never normalized: every offset must index the exact input. Patterns carry their own tolerance for
case (re.IGNORECASE), dashes (-, en dash, em dash), apostrophes (' and curly) and whitespace (\\s matches NBSP).
"""

import re
from bisect import bisect_right
from collections.abc import Iterator
from decimal import Decimal

from checks.engine.types import Span

DASH = "[-\u2013\u2014]"
APOS = "['\u2019]"
QUOTE_OPEN = '["\u201c]?'
QUOTE_CLOSE = '["\u201d]?'
RANGE_GAP = re.compile(rf"\s*(?:APRs?\s*)?(?:{DASH}|to|and)\s*", re.IGNORECASE)

_SENTENCE_BREAK = re.compile(r"[.!?](?=\s|$)|\n")
_PARAGRAPH_BREAK = re.compile(r"\n[ \t\u00a0]*\n")


def compile_i(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def decimals_of(number: str) -> int:
    return len(number.split(".", 1)[1]) if "." in number else 0


def to_decimal(number: str) -> Decimal:
    return Decimal(number.replace(",", ""))


class Segments:
    """Sentence and paragraph boundaries, precomputed once per text for O(log n) lookups."""

    def __init__(self, text: str) -> None:
        self._len = len(text)
        self._sentence_ends = [m.end() for m in _SENTENCE_BREAK.finditer(text)]
        self._paragraph_ends = [m.end() for m in _PARAGRAPH_BREAK.finditer(text)]

    @staticmethod
    def _bounds(ends: list[int], pos: int, length: int) -> Span:
        i = bisect_right(ends, pos)
        start = ends[i - 1] if i > 0 else 0
        end = ends[i] if i < len(ends) else length
        return Span(start, end)

    def sentence(self, pos: int) -> Span:
        return self._bounds(self._sentence_ends, pos, self._len)

    def paragraph(self, pos: int) -> Span:
        return self._bounds(self._paragraph_ends, pos, self._len)


def window_before(text: str, pos: int, width: int, floor: int = 0) -> str:
    return text[max(floor, pos - width) : pos]


def window_after(text: str, pos: int, width: int, ceil: int | None = None) -> str:
    end = pos + width if ceil is None else min(ceil, pos + width)
    return text[pos:end]


def spans(pattern: re.Pattern[str], text: str, start: int = 0, end: int | None = None) -> Iterator[Span]:
    for m in pattern.finditer(text, start, len(text) if end is None else end):
        yield Span(m.start(), m.end())


def first_span(pattern: re.Pattern[str], text: str, start: int = 0, end: int | None = None) -> Span | None:
    m = pattern.search(text, start, len(text) if end is None else end)
    return Span(m.start(), m.end()) if m else None


def phrase_pattern(phrase: str) -> str:
    """A configured phrase as a regex: literal words, any run of whitespace between them."""
    return r"\s+".join(re.escape(word) for word in phrase.split())
