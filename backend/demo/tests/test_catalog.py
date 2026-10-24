"""The catalog on its own, without a database: every code rule fires on some seeded copy, clean copy exists, and
the scripted AI quotes are real substrings. Fast feedback while writing copy; the seed tests prove the same on the
persisted rows."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from checks.engine import RuleContext, run_code_checks
from checks.engine.registry import CODE_RULES
from checks.llm import LLM_RULES_BY_ID
from core.domain import AttachmentKind, Product
from demo.content import CATALOG
from demo.story import AiResult, Attach, Decide, NewRound, Resubmit, Story, Submit, TermsSpec

NOW = datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
PARTNER_TYPES = {p.key: p.type for p in CATALOG.partners}


@dataclass(frozen=True)
class Seeded:
    story: Story
    index: int
    ctx: RuleContext
    ai: AiResult | None


def _terms_at(product: Product, at: datetime, terms: tuple[TermsSpec, ...]) -> object:
    in_effect = [t for t in terms if t.product == product and t.at.resolve(NOW) <= at]
    return max(in_effect, key=lambda t: t.at.resolve(NOW)).values if in_effect else None


def seeded_versions() -> Iterator[Seeded]:
    for story in CATALOG.stories:
        kinds: set[AttachmentKind] = set()
        for step in story.steps:
            at = step.at.resolve(NOW)
            index: int | None = None
            ai = None
            if isinstance(step, Attach):
                kinds.add(step.kind)
            elif isinstance(step, Submit):
                index, ai = 0, step.ai
            elif isinstance(step, Resubmit | NewRound):
                index, ai = step.text, step.ai
            elif isinstance(step, Decide):
                index = step.edited
            if index is None:
                continue
            terms = _terms_at(story.product, at, CATALOG.terms)
            ctx = RuleContext(
                text=story.versions[index],
                product=story.product,
                channel=story.channel,
                markets=frozenset(story.markets),
                partner_type=PARTNER_TYPES[story.partner] if story.partner else None,
                attachment_kinds=frozenset(kinds),
                terms=terms,  # pyrefly: ignore[bad-argument-type]
                today=at.date(),
            )
            yield Seeded(story, index, ctx, ai if isinstance(ai, AiResult) else None)


def test_every_code_rule_fires_on_some_seeded_version() -> None:
    fired = {f.rule_id for s in seeded_versions() for f in run_code_checks(s.ctx).findings}
    code_rules = {r.spec.id for r in CODE_RULES}
    assert code_rules - fired == set()


def test_clean_copy_exists() -> None:
    clean = [s for s in seeded_versions() if not run_code_checks(s.ctx).findings]
    assert len(clean) >= 10


@pytest.mark.parametrize("seeded", [s for s in seeded_versions() if s.ai is not None and s.ai.findings], ids=str)
def test_every_ai_quote_is_in_its_text_and_its_rule_applies(seeded: Seeded) -> None:
    assert seeded.ai is not None
    for finding in seeded.ai.findings:
        assert finding.quote in seeded.ctx.text
        assert finding.rule_id in LLM_RULES_BY_ID


def test_story_keys_and_titles_are_unique() -> None:
    assert len({s.key for s in CATALOG.stories}) == len(CATALOG.stories)
    assert len({s.title for s in CATALOG.stories}) == len(CATALOG.stories)


def test_steps_are_in_time_order() -> None:
    for story in CATALOG.stories:
        times = [step.at.resolve(NOW) for step in story.steps]
        assert times == sorted(times), story.key
        assert isinstance(story.steps[0], Submit), story.key
