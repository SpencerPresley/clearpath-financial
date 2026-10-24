"""Engine configuration that compliance may tune without a code change to the rules themselves."""

from dataclasses import dataclass

# Cal. Fin. Code §22162 prescribes no wording, only that the printed text discloses the license the loan is
# made or arranged under. Matching is case-insensitive and whitespace-tolerant.
CA_LICENSE_PHRASES: tuple[str, ...] = (
    "Loans made or arranged pursuant to a California Financing Law license",
    "California Financing Law license",
    "California Finance Lenders Law license",
    "CFL license",
)


# The postal address CAN-SPAM suggestions offer: the company's own (the address the demo content uses), kept here so
# compliance can change it without touching a rule. A rule must never make one up (walkthrough B2's audit).
POSTAL_ADDRESS = "ClearPath Financial, Inc., 500 Market Street, Suite 1200, San Francisco, CA 94105"


@dataclass(frozen=True)
class EngineConfig:
    ca_license_phrases: tuple[str, ...] = CA_LICENSE_PHRASES
    postal_address: str = POSTAL_ADDRESS


DEFAULT_CONFIG = EngineConfig()
