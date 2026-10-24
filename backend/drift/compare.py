"""Locating the approved copy on a fetched page (product-spec "Drift monitoring", step 3).

We don't diff the whole page: navigation, dates and ads change constantly (decisions.md). Instead:

1. Normalize both texts (Unicode compatibility forms, straight quotes and dashes, one space for any whitespace), so
   markup, line breaks and typography don't count as edits.
2. The approved copy appears verbatim → `unchanged`.
3. Otherwise `rapidfuzz.fuzz.partial_ratio_alignment` finds the page region that best matches the copy. The region
   is widened (an inserted sentence pushes the end of the copy past the aligned window), word-diffed against the
   approved copy, and the page-only text at either end is trimmed off.
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


def _snap(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen [start, end) to whole words."""
    if start > 0:
        start = text.rfind(" ", 0, start) + 1
    if end < len(text):
        found = text.find(" ", end)
        end = len(text) if found < 0 else found
    return start, end


def _is_filler(segment: DiffSegment) -> bool:
    return segment.op is DiffOp.EQUAL and _FILLER.fullmatch(segment.text) is not None


def _tidy(segments: tuple[DiffSegment, ...]) -> tuple[DiffSegment, ...]:
    """Make the word diff readable and drop page-only text at either end.

    Spaces and punctuation that happen to match between two changed words ("Checking your rate" against "Advertiser
    disclosure") are folded into the change, so each changed stretch reads as one deletion and one insertion.
    Insertions before the first and after the last kept word of the approved copy are the rest of the page, not
    edits, and are dropped.
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
        at_edge = i < first_kept or j - 1 > last_kept
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
    copy, text = normalize(approved), normalize(page)
    if copy in text:
        return Comparison(result=DriftResult.UNCHANGED, score=100.0, matched_text=copy, diff=())
    if not text:
        return _missing(0.0)
    alignment = fuzz.partial_ratio_alignment(copy, text)
    if alignment is None:  # only with a score_cutoff; kept for the type
        return _missing(0.0)
    slack = max(40, len(copy) // 4)
    start, end = _snap(text, max(0, alignment.dest_start - slack), min(len(text), alignment.dest_end + slack))
    diff = _tidy(diff_texts(copy, text[start:end]))
    region = "".join(s.text for s in diff if s.op is not DiffOp.DELETE).strip()
    score = float(fuzz.ratio(copy, region))
    if score < MISSING_BELOW:
        return _missing(score)
    return Comparison(result=DriftResult.MODIFIED, score=score, matched_text=region, diff=diff)
