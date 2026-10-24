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


@dataclass(frozen=True)
class EngineConfig:
    ca_license_phrases: tuple[str, ...] = CA_LICENSE_PHRASES


DEFAULT_CONFIG = EngineConfig()
