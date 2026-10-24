"""samples/README.md, parsed. The README is generated from the same data as the workbook (reports/sample-tracker.md),
so the importer's tests read its tables directly instead of a hand copy that could drift from it."""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

README = Path(__file__).resolve().parents[3] / "samples" / "README.md"

_ROW_REF = re.compile(r"r(\d+)")
_LINK_REF = re.compile(r"(MCR-\d{2}-\d{3}) \(r(\d+)\)")


@dataclass(frozen=True)
class MessRow:
    """One row of an "Intended messiness" table."""

    kind: str  # the ### heading, e.g. "Status spelling variants"
    request_id: str
    rows: tuple[int, ...]
    column: str
    raw: str | None  # None for (empty); otherwise the text inside the backticks, quotes removed
    expected: str


@dataclass(frozen=True)
class RawValueRow:
    """One row of an "Every raw value, mapped" table."""

    table: str  # "Status values", "Product values", ...
    raw: str | None
    canonical: str
    count: int


def _raw(cell: str) -> str | None:
    inner = cell.strip().strip("`")
    if inner == "(empty)":
        return None
    if inner.startswith('"') and inner.endswith('"'):
        return inner[1:-1]
    return inner


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _sections(text: str, level: str) -> dict[str, str]:
    parts = re.split(rf"^{level} (.+)$", text, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts), 2)}


def _table_lines(body: str) -> list[list[str]]:
    lines = [ln for ln in body.splitlines() if ln.startswith("|")]
    return [_cells(ln) for ln in lines[2:]]  # skip header and the |---| rule


@cache
def readme() -> str:
    return README.read_text()


@cache
def mess_rows() -> tuple[MessRow, ...]:
    messiness = _sections(readme(), "##")["Intended messiness (the oracle)"]
    out = []
    for kind, body in _sections(messiness, "###").items():
        for cells in _table_lines(body):
            request_id, rows, column, raw, expected = cells
            out.append(
                MessRow(
                    kind=kind,
                    request_id=request_id,
                    rows=tuple(int(n) for n in _ROW_REF.findall(rows)),
                    column=column,
                    raw=_raw(raw),
                    expected=expected,
                )
            )
    return tuple(out)


def mess(kind: str) -> tuple[MessRow, ...]:
    rows = tuple(r for r in mess_rows() if r.kind == kind)
    assert rows, f"no oracle rows for {kind!r}"
    return rows


@cache
def raw_value_rows() -> tuple[RawValueRow, ...]:
    mapped = _sections(readme(), "##")["Every raw value, mapped"]
    out = []
    for table, body in _sections(mapped, "###").items():
        if not body.lstrip().startswith("|"):
            continue  # "Clean labels to app vocabulary" is a list, not a table
        for cells in _table_lines(body):
            raw, canonical, count = cells[0], cells[1], cells[2]
            out.append(RawValueRow(table=table, raw=_raw(raw), canonical=canonical, count=int(count)))
    return tuple(out)


def raw_values(table: str) -> tuple[RawValueRow, ...]:
    rows = tuple(r for r in raw_value_rows() if r.table == table)
    assert rows, f"no oracle rows for {table!r}"
    return rows


def link_rows(column: str, label: str) -> tuple[int, ...]:
    """Row numbers from the "Links: hyperlink objects vs text" bullets, e.g. ("Asset Name / File Link",
    "hyperlinked cells")."""
    links = _sections(_sections(readme(), "##")["Intended messiness (the oracle)"], "###")[
        "Links: hyperlink objects vs text"
    ]
    blocks = re.split(r"^- \*\*(.+?)\*\*:", links, flags=re.MULTILINE)
    by_column = {blocks[i]: blocks[i + 1] for i in range(1, len(blocks), 2)}
    for line in by_column[column].splitlines():
        head = line.split(":", 1)[0]
        if label in head:
            return tuple(int(r) for _, r in _LINK_REF.findall(line))
    raise AssertionError(f"no link list {label!r} under {column!r}")


def bullet_rows(label: str) -> tuple[int, ...]:
    """Row numbers from an "Other characteristics" bullet, by its bold label."""
    for line in readme().splitlines():
        if line.startswith(f"- **{label}"):
            return tuple(int(r) for _, r in _LINK_REF.findall(line))
    raise AssertionError(f"no bullet {label!r}")
