"""The demo catalog: who works at ClearPath, its partners and offer terms, and every seeded item's story."""

from typing import Final

from demo.content.calendar import GO_LIVE, TRACKER_IMPORTED
from demo.content.cards import CC_STORIES
from demo.content.mortgages import MTG_STORIES
from demo.content.people import PARTNERS, PERSONAS, TERMS
from demo.content.personal_loans import PL_STORIES
from demo.story import Catalog, ImportTracker, ReleaseQueue, SetAvailability, day

CATALOG: Final = Catalog(
    personas=PERSONAS,
    partners=PARTNERS,
    terms=TERMS,
    stories=(*PL_STORIES, *CC_STORIES, *MTG_STORIES),
    events=(
        SetAvailability(day(2, "08:00"), "leah", available=False),
        ReleaseQueue(
            day(2, "08:05"),
            "leah",
            reason="Leah is out until next Tuesday; back to the pool.",
            cover="sam",
            cover_reason="Covering for Leah while she's out.",
        ),
        ImportTracker(day(1, "17:30"), dated=TRACKER_IMPORTED),
    ),
    go_live=GO_LIVE,
)
