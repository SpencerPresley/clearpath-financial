"""When ClearPath switched from the Excel tracker to the app."""

from typing import Final

from demo.story import day

# Monday ten weeks before the seed. The sample tracker (samples/README.md) was last touched the Friday before,
# 2026-08-14, and the importer brings that history in as legacy items; everything the seed writes natively happens
# on or after this instant (demo/tests/test_seed.py checks both sides). Moving it earlier than the tracker's end
# overlaps the two histories.
GO_LIVE: Final = day(68, "08:00")
