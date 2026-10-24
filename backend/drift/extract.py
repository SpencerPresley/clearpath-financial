"""Visible text of a static HTML page: what a reader sees, one block per line.

BeautifulSoup with the standard library's `html.parser`: pure Python, so no native parser runs on hostile HTML.
Dropped: script, style, noscript, template, svg, iframe and other embeds, the head (its title is returned
separately), and anything hidden with the `hidden` attribute, `aria-hidden="true"` or an inline `display: none` /
`visibility: hidden`. Content hidden by stylesheets or revealed by scripts is not seen (no rendering).
"""

import re
from dataclasses import dataclass
from typing import Final

from bs4 import BeautifulSoup, Tag

MAX_TEXT_CHARS: Final = 100_000  # the intake copy limit (SubmitItemIn.content_text)

_DROP: Final = (
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


def visible_text(html: str) -> PageText:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(" ", strip=True) or None if title_tag is not None else None
    for tag in soup.find_all(_DROP):
        tag.decompose()
    for tag in soup.find_all(_hidden):
        if not tag.decomposed:
            tag.decompose()
    for tag in soup.find_all("br"):
        tag.replace_with("\n")
    for tag in soup.find_all(_BLOCK):
        tag.insert_before("\n")
        tag.insert_after("\n")
    lines = (_SPACES.sub(" ", line).strip() for line in soup.get_text().splitlines())
    return PageText(title=title, text=_cap("\n".join(line for line in lines if line)))
