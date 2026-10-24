"""Rule families. Each module exposes RULES: tuple[Rule, ...]."""

from checks.engine.rule import Rule
from checks.engine.rules import california, card, channel, claims, closed_end, human, mortgage, prescreen, pricing

ALL_RULES: tuple[Rule, ...] = (
    *closed_end.RULES,
    *pricing.RULES,
    *card.RULES,
    *mortgage.RULES,
    *claims.RULES,
    *prescreen.RULES,
    *channel.RULES,
    *california.RULES,
    *human.RULES,
)
