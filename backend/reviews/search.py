"""Precedent search (decisions.md "Search"): lexical first, both channels taking `ItemFilter`.

- `find_phrase`: case-insensitive substring over version text, backed by the trigram GIN index, ranked by
  trigram word similarity.
- `search_text`: `websearch_to_tsquery` over the generated tsvector, ranked by `ts_rank_cd`.

Both search only versions that ever received an approval (precedent), one hit per item (its latest matching
such version). Snippets are structured parts, not HTML: version text is untrusted affiliate copy, and
`ts_headline` doesn't escape it.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from django.contrib.postgres.search import SearchHeadline, SearchQuery, SearchRank, TrigramWordSimilarity
from django.db.models import Exists, F, OuterRef, QuerySet, Subquery

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import Channel, DecisionOutcome, ItemStatus, Product
from reviews.filters import ItemFilter
from reviews.models import APPROVED_OUTCOMES, Decision, ReviewItem, Version
from reviews.selectors import filter_items


class SearchMode(StrEnum):
    PHRASE = "phrase"
    TEXT = "text"


_START, _STOP = "\x02", "\x03"  # highlight markers: control characters ordinary copy never contains
_CONTEXT: Final = 80
_ELLIPSIS: Final = "…"


@dataclass(frozen=True)
class SnippetPart:
    text: str
    highlighted: bool


@dataclass(frozen=True)
class SearchHit:
    item_id: int
    key: str
    title: str
    status: ItemStatus
    product: Product
    channel: Channel
    partner_name: str | None
    version_id: int
    version_n: int
    snippet: tuple[SnippetPart, ...]
    score: float
    version_outcome: DecisionOutcome | None
    version_decided_at: datetime | None


def _latest_matching_versions(items: QuerySet[ReviewItem], matching: QuerySet[Version]) -> QuerySet[Version]:
    # Precedent is approved wording (ledger ruling): only versions that ever received an approving decision,
    # whatever the item's status is now (shown as a badge). Copy still under review isn't precedent.
    ever_approved = Exists(Decision.objects.filter(version=OuterRef("pk"), outcome__in=APPROVED_OUTCOMES))
    latest = matching.filter(ever_approved, item__in=items).order_by("item_id", "-n").distinct("item_id").values("pk")
    # The matched version's own decision: "was this wording approved?" is about the text that contains it.
    decisions = Decision.objects.filter(version=OuterRef("pk")).order_by("-decided_at", "-pk")
    return (
        Version.objects.filter(pk__in=Subquery(latest))
        .select_related("item", "item__partner")
        .annotate(
            version_outcome=Subquery(decisions.values("outcome")[:1]),
            version_decided_at=Subquery(decisions.values("decided_at")[:1]),
        )
    )


def _hit(version: Version, snippet: tuple[SnippetPart, ...], score: float) -> SearchHit:
    item = version.item
    outcome = getattr(version, "version_outcome", None)
    return SearchHit(
        item_id=item.pk,
        key=item.key,
        title=item.title,
        status=ItemStatus(item.status),
        product=Product(item.product),
        channel=Channel(item.channel),
        partner_name=item.partner.name if item.partner else None,
        version_id=version.pk,
        version_n=version.n,
        snippet=snippet,
        score=score,
        version_outcome=DecisionOutcome(outcome) if outcome else None,
        version_decided_at=getattr(version, "version_decided_at", None),
    )


def _mark_cuts(parts: tuple[SnippetPart, ...], *, before: bool, after: bool) -> tuple[SnippetPart, ...]:
    """A "…" on each side where the snippet stops short of the version text."""
    lead = (SnippetPart(_ELLIPSIS, highlighted=False),) if parts and before else ()
    tail = (SnippetPart(_ELLIPSIS, highlighted=False),) if parts and after else ()
    return lead + parts + tail


def _elide_headline(parts: tuple[SnippetPart, ...], text: str) -> tuple[SnippetPart, ...]:
    # ts_headline returns a contiguous excerpt of whole words; find where it sits to know which ends were cut.
    shown = "".join(p.text for p in parts)
    at = text.find(shown)
    if at < 0:
        return parts
    return _mark_cuts(parts, before=at > 0, after=at + len(shown) < len(text))


def _window(text: str, phrase: str) -> tuple[SnippetPart, ...]:
    at = text.lower().find(phrase.lower())
    if at < 0:  # icontains and str.lower() can disagree on a few characters: show the opening instead
        at = end_of_phrase = 0
        context = _CONTEXT * 2
    else:
        end_of_phrase, context = at + len(phrase), _CONTEXT
    start, end = max(at - _CONTEXT, 0), min(end_of_phrase + context, len(text))
    # Snap the cuts to word boundaries, never into the phrase itself.
    if start > 0 and not text[start - 1].isspace():
        space = text.find(" ", start, at)
        start = at if space < 0 else space + 1
    if end < len(text) and not text[end].isspace():
        space = text.rfind(" ", end_of_phrase, end)
        end = end_of_phrase if space < 0 else space
    parts = (
        SnippetPart(text[start:at].lstrip(), highlighted=False),
        SnippetPart(text[at:end_of_phrase], highlighted=True),
        SnippetPart(text[end_of_phrase:end].rstrip(), highlighted=False),
    )
    return _mark_cuts(tuple(p for p in parts if p.text), before=start > 0, after=end < len(text))


def _parse_headline(headline: str) -> tuple[SnippetPart, ...]:
    parts: list[SnippetPart] = []
    for i, chunk in enumerate(headline.replace(_STOP, _START).split(_START)):
        if chunk:
            parts.append(SnippetPart(chunk, highlighted=i % 2 == 1))
    return tuple(parts)


def find_phrase(
    *, viewer: User, phrase: str, filters: ItemFilter, limit: int = 20, clock: Clock = SYSTEM_CLOCK
) -> tuple[SearchHit, ...]:
    phrase = phrase.strip()
    if not phrase:
        return ()
    items = filter_items(viewer=viewer, filters=filters, clock=clock)
    versions = (
        _latest_matching_versions(items, Version.objects.filter(content_text__icontains=phrase))
        .annotate(score=TrigramWordSimilarity(phrase, "content_text"))
        .order_by("-score", "-item_id")[:limit]
    )
    return tuple(_hit(v, _window(v.content_text, phrase), float(v.score)) for v in versions)  # pyrefly: ignore[missing-attribute]


def search_text(
    *, viewer: User, query: str, filters: ItemFilter, limit: int = 20, clock: Clock = SYSTEM_CLOCK
) -> tuple[SearchHit, ...]:
    query = query.strip()
    if not query:
        return ()
    ts_query = SearchQuery(query, search_type="websearch", config="english")
    items = filter_items(viewer=viewer, filters=filters, clock=clock)
    versions = (
        _latest_matching_versions(items, Version.objects.filter(search_vector=ts_query))
        .annotate(
            score=SearchRank(F("search_vector"), ts_query, cover_density=True),
            headline=SearchHeadline(
                "content_text", ts_query, config="english", start_sel=_START, stop_sel=_STOP, max_words=40, min_words=15
            ),
        )
        .order_by("-score", "-item_id")[:limit]
    )
    return tuple(
        _hit(v, _elide_headline(_parse_headline(v.headline), v.content_text), float(v.score))  # pyrefly: ignore[missing-attribute]
        for v in versions
    )


@dataclass(frozen=True)
class SearchResults:
    mode: SearchMode
    query: str
    hits: tuple[SearchHit, ...]


def search_library(
    *, viewer: User, query: str, mode: SearchMode, filters: ItemFilter, limit: int = 20, clock: Clock = SYSTEM_CLOCK
) -> SearchResults:
    """Precedent search in either mode: `phrase` for exact wording, `text` for full-text."""
    if mode is SearchMode.PHRASE:
        hits = find_phrase(viewer=viewer, phrase=query, filters=filters, limit=limit, clock=clock)
    else:
        hits = search_text(viewer=viewer, query=query, filters=filters, limit=limit, clock=clock)
    return SearchResults(mode=mode, query=query, hits=hits)
