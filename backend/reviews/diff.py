"""Word-level diff between two versions' text (the "compare with" view and the fast-track diff)."""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

# Numbers stay whole ("7.49", "10,000") so a rate change reads as one replacement, not three.
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|\w+|\s+|[^\w\s]")


class DiffOp(StrEnum):
    EQUAL = "equal"
    INSERT = "insert"
    DELETE = "delete"


@dataclass(frozen=True)
class DiffSegment:
    op: DiffOp
    text: str


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def diff_texts(old: str, new: str) -> tuple[DiffSegment, ...]:
    """Segments in reading order. Joining the non-insert segments gives `old`; non-delete gives `new`."""
    a, b = _tokens(old), _tokens(new)
    raw: list[DiffSegment] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            raw.append(DiffSegment(DiffOp.EQUAL, "".join(a[i1:i2])))
            continue
        if i2 > i1:
            raw.append(DiffSegment(DiffOp.DELETE, "".join(a[i1:i2])))
        if j2 > j1:
            raw.append(DiffSegment(DiffOp.INSERT, "".join(b[j1:j2])))
    merged: list[DiffSegment] = []
    for segment in raw:
        if merged and merged[-1].op is segment.op:
            merged[-1] = DiffSegment(segment.op, merged[-1].text + segment.text)
        else:
            merged.append(segment)
    return tuple(merged)
