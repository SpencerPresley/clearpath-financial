"""Precedent search (decisions.md "Search"): lexical first, both channels taking `ItemFilter`.

- `find_phrase`: case-insensitive substring over version text, backed by the trigram GIN index, ranked by
  trigram word similarity.
- `search_text`: `websearch_to_tsquery` over the generated tsvector, ranked by `ts_rank_cd`.

Each returns at most one hit per item (its latest matching version). Snippets are structured parts, not
HTML: version text is untrusted affiliate copy, and `ts_headline` doesn't escape it.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from django.contrib.postgres.search import SearchHeadline, SearchQuery, SearchRank, TrigramWordSimilarity
from django.db.models import F, OuterRef, QuerySet, Subquery

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import Channel, DecisionOutcome, ItemStatus, Product
from reviews.filters import ItemFilter
from reviews.models import Decision, ReviewItem, Version
from reviews.selectors import filter_items


class SearchMode(StrEnum):
    PHRASE = "phrase"
    TEXT = "text"


_START, _STOP = "\x02", "\x03"  # highlight markers: control characters ordinary copy never contains
_CONTEXT: Final = 80


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
    latest = matching.filter(item__in=items).order_by("item_id", "-n").distinct("item_id").values("pk")
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


def _window(text: str, phrase: str) -> tuple[SnippetPart, ...]:
    at = text.lower().find(phrase.lower())
    if at < 0:
        return (SnippetPart(text[: _CONTEXT * 2], highlighted=False),)
    start, end = max(at - _CONTEXT, 0), min(at + len(phrase) + _CONTEXT, len(text))
    parts = [
        SnippetPart(text[start:at], highlighted=False),
        SnippetPart(text[at : at + len(phrase)], highlighted=True),
        SnippetPart(text[at + len(phrase) : end], highlighted=False),
    ]
    return tuple(p for p in parts if p.text)


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
        _hit(v, _parse_headline(v.headline), float(v.score))  # pyrefly: ignore[missing-attribute]
        for v in versions
    )
