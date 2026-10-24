"""Visible text of a static HTML page: what a reader sees, one block per line.

BeautifulSoup with the standard library's `html.parser`: pure Python, so no native parser runs on hostile HTML.
Dropped: script, style, noscript, template, svg, iframe and other embeds, the head (its title is returned
separately), and anything hidden with the `hidden` attribute, `aria-hidden="true"` or an inline `display: none` /
`visibility: hidden`. Content hidden by stylesheets or revealed by scripts is not seen (no rendering).
"""

import re
from dataclasses import dataclass
from typing import Final

from bs4 import BeautifulSoup, CData, NavigableString, PageElement, Tag

MAX_TEXT_CHARS: Final = 100_000  # the intake copy limit (SubmitItemIn.content_text)

_DROP: Final = frozenset(
    (
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "iframe",
        "object",
        "embed",
        "canvas",
        "head",
    )
)
_BLOCK: Final = frozenset(
    [
        "address",
        "article",
        "aside",
        "blockquote",
        "caption",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "legend",
        "li",
        "main",
        "nav",
        "ol",
        "option",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    ]
)
_TEXT: Final = (NavigableString, CData)  # exact types: bs4's Comment, Doctype, Script... subclass NavigableString
_HIDDEN_STYLE: Final = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)
_SPACES: Final = re.compile(r"[^\S\n]+")


@dataclass(frozen=True)
class PageText:
    title: str | None
    text: str


def _hidden(tag: Tag) -> bool:
    if tag.has_attr("hidden") or str(tag.get("aria-hidden", "")).lower() == "true":
        return True
    style = tag.get("style")
    return isinstance(style, str) and _HIDDEN_STYLE.search(style) is not None


def _cap(text: str) -> str:
    if len(text) <= MAX_TEXT_CHARS:
        return text
    cut = text.rfind(" ", 0, MAX_TEXT_CHARS)
    return text[: cut if cut > 0 else MAX_TEXT_CHARS]


def _text_of(root: Tag) -> str:
    """Visible strings in document order, with a line break around each block. One iterative pass over the tree
    that never mutates it: bs4's insert/decompose are O(depth) each, so mutating every block of a deeply nested
    page (80 000 nested divs) is quadratic, minutes of CPU from a 400 KB page."""
    out: list[str] = []
    stack: list[tuple[PageElement, bool]] = [(root, False)]
    while stack:
        node, closing = stack.pop()
        if closing:
            out.append("\n")
        elif type(node) in _TEXT:  # not comments, doctypes, script/style strings
            out.append(str(node))
        elif isinstance(node, Tag):
            if node.name in _DROP or _hidden(node):
                continue
            if node.name == "br":
                out.append("\n")
                continue
            if node.name in _BLOCK:
                out.append("\n")
                stack.append((node, True))
            stack.extend((child, False) for child in reversed(node.contents))
    return "".join(out)


def visible_text(html: str) -> PageText:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(" ", strip=True) or None if title_tag is not None else None
    lines = (_SPACES.sub(" ", line).strip() for line in _text_of(soup).splitlines())
    return PageText(title=title, text=_cap("\n".join(line for line in lines if line)))
