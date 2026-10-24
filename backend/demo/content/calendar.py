"""When ClearPath switched from the Excel tracker to the app."""

from typing import Final

from demo.story import day

# Monday ten weeks before the seed. The sample tracker (samples/README.md) was last touched the Friday before,
# 2026-08-14, and the importer brings that history in as legacy items; everything the seed writes natively happens
# on or after this instant (demo/tests/test_seed.py checks both sides). Moving it earlier than the tracker's end
# overlaps the two histories.
GO_LIVE: Final = day(68, "08:00")

# The tracker import is dated go-live morning, once the partners are entered (GO_LIVE + a minute each), so Recent
# imports and each legacy item's history put it where the story does. It replays later (`ImportTracker.at`): item
# keys follow replay order, and docs/demo.md cites the native ones (CP-1..CP-43, then legacy, then CP-222).
TRACKER_IMPORTED: Final = day(68, "08:30")
