"""Deterministic compliance checks on marketing copy. Pure Python; no Django.

`run_code_checks` is fast enough to run on every keystroke; `human_checklist` lists what a reviewer must look at
by hand; `render_fast_track` rewrites quoted offer terms after a terms change.
"""

from checks.engine.config import DEFAULT_CONFIG, EngineConfig
from checks.engine.fast_track import StaleTermsRef, render_fast_track
from checks.engine.registry import ENGINE_VERSION, RULES, RULESET_VERSION, human_checklist, run_code_checks
from checks.engine.types import CheckResult, FindingDraft, RuleContext, RuleSpec, Span, TermsRefDraft

__all__ = [
    "DEFAULT_CONFIG",
    "ENGINE_VERSION",
    "RULES",
    "RULESET_VERSION",
    "CheckResult",
    "EngineConfig",
    "FindingDraft",
    "RuleContext",
    "RuleSpec",
    "Span",
    "StaleTermsRef",
    "TermsRefDraft",
    "human_checklist",
    "render_fast_track",
    "run_code_checks",
]
