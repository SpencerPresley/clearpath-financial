"""The rule set and the two entry points that run it."""

from collections.abc import Mapping
from types import MappingProxyType

from checks.engine.config import DEFAULT_CONFIG, EngineConfig
from checks.engine.extract import Analysis, analyze
from checks.engine.rule import Rule, applies, to_finding
from checks.engine.rules import ALL_RULES
from checks.engine.types import CheckResult, FindingDraft, RuleContext, RuleSpec, TermsRefDraft

CODE_RULES: tuple[Rule, ...] = tuple(r for r in ALL_RULES if r.spec.kind == "code")
HUMAN_RULES: tuple[Rule, ...] = tuple(r for r in ALL_RULES if r.spec.kind == "human")


def _index(rules: tuple[Rule, ...]) -> Mapping[str, RuleSpec]:
    specs: dict[str, RuleSpec] = {}
    for rule in rules:
        if rule.spec.id in specs:
            raise ValueError(f"duplicate rule id {rule.spec.id}")
        specs[rule.spec.id] = rule.spec
    return MappingProxyType(specs)


RULES: Mapping[str, RuleSpec] = _index(ALL_RULES)
# The rule-set date a decision records: the latest date any rule (as written) took effect.
RULESET_VERSION = max(spec.effective_from for spec in RULES.values())
# Bump on ANY change to engine behavior (a regex, a severity, a message). RULESET_VERSION only moves when the law
# does, so a check-result cache keyed on content hash must include this too or it serves stale findings.
ENGINE_VERSION = "2026-10-24.2"


def _sort_key(f: FindingDraft) -> tuple[int, int, str, str]:
    if f.span is None:
        return (1, 0, f.rule_id, f.message)
    return (0, f.span.start, f.rule_id, f.message)


def _run(
    rules: tuple[Rule, ...], ctx: RuleContext, config: EngineConfig, analysis: Analysis
) -> tuple[FindingDraft, ...]:
    findings: dict[tuple[str, object, str], FindingDraft] = {}
    for rule in rules:
        if not applies(rule.spec, ctx):
            continue
        for hit in rule.check(ctx, analysis, config):
            finding = to_finding(rule.spec, hit, ctx.text)
            findings.setdefault((finding.rule_id, finding.span, finding.message), finding)
    return tuple(sorted(findings.values(), key=_sort_key))


def run_code_checks(ctx: RuleContext, *, config: EngineConfig = DEFAULT_CONFIG) -> CheckResult:
    analysis = analyze(ctx.text, ctx.product, ctx.terms)
    refs = tuple(TermsRefDraft(field=c.field, span=c.span, quoted_value=c.value) for c in analysis.claims)
    return CheckResult(findings=_run(CODE_RULES, ctx, config, analysis), terms_refs=refs)


def human_checklist(ctx: RuleContext) -> tuple[FindingDraft, ...]:
    return _run(HUMAN_RULES, ctx, DEFAULT_CONFIG, analyze(ctx.text, ctx.product, ctx.terms))
