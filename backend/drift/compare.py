"""Locating the approved copy on a fetched page (product-spec "Drift monitoring", step 3).

We don't diff the whole page: navigation, dates and ads change constantly (decisions.md). Instead:

1. Normalize both texts (Unicode compatibility forms, straight quotes and dashes, one space for any whitespace), so
   markup, line breaks and typography don't count as edits.
2. The approved copy appears verbatim → `unchanged`.
3. Otherwise `rapidfuzz.fuzz.partial_ratio_alignment` finds the page window that best matches the copy. The region
   compared is the whole page lines (blocks) that window touches, so an edit at either end of the copy stays in the
   diff while neighbouring blocks (navigation, other offers) stay out. When a line runs far past the window (a page
   that is one long block), the region is clamped to the window plus some slack and page-only text at the clamped
   end is dropped from the diff.
4. The score is `fuzz.ratio(approved, region)`: how much of the approved copy survives there. At or above
   `MISSING_BELOW` the copy is `modified` (with the diff); below it the copy is `missing`.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

from rapidfuzz import fuzz

from core.domain import DriftResult
from reviews.diff import DiffOp, DiffSegment, diff_texts

MISSING_BELOW: Final = 60.0

# Code points, not literals (formatters and linters fight over look-alike characters): U+2018-201B and U+2032
# (single quotes, prime), U+201C-201F and U+2033 (double quotes), U+2010-2015 and U+2212 (hyphens, dashes, minus).
_TYPOGRAPHY: Final = str.maketrans(
    dict.fromkeys((8216, 8217, 8218, 8219, 8242), "'")
    | dict.fromkeys((8220, 8221, 8222, 8223, 8243), '"')
    | dict.fromkeys((8208, 8209, 8210, 8211, 8212, 8213, 8722), "-")
)
_WHITESPACE: Final = re.compile(r"\s+")
_FILLER: Final = re.compile(r"[\W_]*")  # no letters or digits


@dataclass(frozen=True)
class Comparison:
    result: DriftResult
    score: float  # 0-100: how much of the approved copy the best-matching region keeps
    matched_text: str  # the page region compared, normalized ("" when missing)
    diff: tuple[DiffSegment, ...]  # approved -> page region; empty unless modified


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHY)
    return _WHITESPACE.sub(" ", folded).strip()


def _region(lines: str, start: int, end: int, slack: int) -> tuple[int, int, bool, bool]:
    """[start, end) widened to whole lines; clamped to `slack` (on word boundaries) where a line runs further.
    Returns the bounds and whether each end was clamped."""
    lo = lines.rfind("\n", 0, start) + 1
    hi = lines.find("\n", end)
    hi = len(lines) if hi < 0 else hi
    clamp_lo, clamp_hi = start - lo > slack, hi - end > slack
    if clamp_lo:
        lo = lines.rfind(" ", 0, start - slack) + 1
    if clamp_hi:
        found = lines.find(" ", end + slack)
        hi = len(lines) if found < 0 else found
    return lo, hi, clamp_lo, clamp_hi


def _shed_edge_lines(copy: str, lines: str, lo: int, hi: int) -> tuple[int, int]:
    """Drop whole lines at either end of the region while that makes it match the copy better (a heading the window
    grazed, the next block's first words)."""

    def score(a: int, b: int) -> float:
        return fuzz.ratio(copy, lines[a:b].replace("\n", " "))

    while (cut := lines.find("\n", lo, hi)) >= 0 and score(cut + 1, hi) > score(lo, hi):
        lo = cut + 1
    while (cut := lines.rfind("\n", lo, hi)) >= 0 and score(lo, cut) > score(lo, hi):
        hi = cut
    return lo, hi


def _is_filler(segment: DiffSegment) -> bool:
    return segment.op is DiffOp.EQUAL and _FILLER.fullmatch(segment.text) is not None


def _tidy(segments: tuple[DiffSegment, ...], *, drop_leading: bool, drop_trailing: bool) -> tuple[DiffSegment, ...]:
    """Make the word diff readable and, at a clamped end, drop page-only text.

    Spaces and punctuation that happen to match between two changed words ("Checking your rate" against "Advertiser
    disclosure") are folded into the change, so each changed stretch reads as one deletion and one insertion.
    At a clamped end (see `_region`), insertions before the first or after the last kept word of the approved copy
    are the rest of a long block, not edits, and are dropped.
    """
    n = len(segments)
    kept_words = [i for i, s in enumerate(segments) if s.op is DiffOp.EQUAL and not _is_filler(s)]
    first_kept, last_kept = (kept_words[0], kept_words[-1]) if kept_words else (n, -1)

    def changed(i: int) -> bool:
        s = segments[i]
        if s.op is not DiffOp.EQUAL:
            return True
        if not _is_filler(s):
            return False
        outside = i < first_kept or i > last_kept
        between = 0 < i < n - 1 and segments[i - 1].op is not DiffOp.EQUAL and segments[i + 1].op is not DiffOp.EQUAL
        return outside or between

    in_change = [changed(i) for i in range(n)]
    out: list[DiffSegment] = []
    i = 0
    while i < n:
        if not in_change[i]:
            out.append(segments[i])
            i += 1
            continue
        j = i
        while j < n and in_change[j]:
            j += 1
        run = segments[i:j]
        at_edge = (drop_leading and i < first_kept) or (drop_trailing and j - 1 > last_kept)
        deleted = "".join(s.text for s in run if s.op is not DiffOp.INSERT)
        inserted = "".join(s.text for s in run if s.op is not DiffOp.DELETE)
        if deleted.strip():
            out.append(DiffSegment(DiffOp.DELETE, deleted))
        if inserted.strip() and not at_edge:
            out.append(DiffSegment(DiffOp.INSERT, inserted))
        i = j
    return tuple(out)


def _missing(score: float) -> Comparison:
    return Comparison(result=DriftResult.MISSING, score=score, matched_text="", diff=())


def compare(approved: str, page: str) -> Comparison:
    copy = normalize(approved)
    lines = "\n".join(line for line in (normalize(raw) for raw in page.splitlines()) if line)
    flat = lines.replace("\n", " ")  # same offsets as `lines`
    if copy in flat:
        return Comparison(result=DriftResult.UNCHANGED, score=100.0, matched_text=copy, diff=())
    if not flat:
        return _missing(0.0)
    alignment = fuzz.partial_ratio_alignment(copy, flat)
    if alignment is None:  # only with a score_cutoff; kept for the type
        return _missing(0.0)
    slack = max(40, len(copy) // 4)
    lo, hi, clamp_lo, clamp_hi = _region(lines, alignment.dest_start, alignment.dest_end, slack)
    lo, hi = _shed_edge_lines(copy, lines, lo, hi)
    diff = _tidy(diff_texts(copy, flat[lo:hi]), drop_leading=clamp_lo, drop_trailing=clamp_hi)
    region = "".join(s.text for s in diff if s.op is not DiffOp.DELETE).strip()
    score = float(fuzz.ratio(copy, region))
    if score < MISSING_BELOW:
        return _missing(score)
    return Comparison(result=DriftResult.MODIFIED, score=score, matched_text=region, diff=diff)
