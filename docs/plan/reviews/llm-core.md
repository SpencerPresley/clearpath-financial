# Review: LLM pre-review core (workstream D phase 1)

Reviewer: one fresh general-purpose subagent, read-only, over `git diff main...HEAD` at `a9d6e21`. It checked
against spec §4.2, §4.3, §5.4, §6.1, §6.3 and §7, decisions.md, the regulations research, the rules-engine
report, and the installed library source (langchain-anthropic, langchain-core, anthropic). It found no blocking
issues, 9 should-fix items and 10 nits.

Resolutions landed in `0d62095` unless marked otherwise. After the fixes: 461 passed and 1 deselected in
`checks`; ruff and pyrefly are clean.

## Should-fix

| # | Finding | Resolution |
|---|---|---|
| 1 | The eval scored invalid outputs (prose, truncated) as empty predictions: true negatives on clean cases, misses on positive ones | **Fixed.** `render` scores only `output_valid` runs and lists invalid ones on their own line. `test_invalid_outputs_are_not_scored` |
| 2 | The creditworthiness guidance was ambiguous on "APRs from X% to Y%", and demanded "lowest rates go only to the most creditworthy" while most corpus ads say only "based on credit" | **Fixed.** Guidance now says a full range is not a lowest-rate claim, and that "based on your credit" does the job. The contradicted-qualifier case is named explicitly |
| 3 | `pl_landing_qualifier_reversed` also matched the net_impression example, and `pl_email_inquiry_scope` had "decision in minutes" | **Fixed both ways.** net_impression now says "use this rule only when no more specific rule covers the claim". The two corpus texts drop the overlapping phrases |
| 4 | "No credit check to see your rate" was exempted, but a soft pull is still a credit check (SH24 §2.8.2) | **Fixed.** The guidance flags any "no credit check" claim when a pull happens. The step-scoping exemption now applies only to score-impact claims. Title: "Credit-check claims match the actual inquiry" |
| 5 | The wording screen skipped `suggested_fix` and missed variants ("non-compliance", "not compliant", NB-hyphen, en dash) | **Fixed.** The pattern is widened (Unicode hyphens U+2010–2014, `complian(t\|ce)`, `not compliant`). A fix containing banned wording becomes `None`, with an adjustment of kind `fix_removed`. Parametrized tests cover 7 variants, a negative ("Compliance may want…") and the fix case |
| 6 | A report whose every item was malformed counted as a valid output | **Fixed.** A non-empty `findings` list with zero parseable items marks the output broken. Tests cover all-malformed (invalid) and partly-malformed (valid) |
| 7 | On models that can't force the tool, thinking spends the 2048-token cap, and strict isn't set though the docs recommend it | **Fixed.** That path binds `report_tool(strict=True)` and gets `MAX_TOKENS_WITH_THINKING = 8192`. It's documented as untested live. The forced Haiku path stays non-strict |
| 8 | Direct imports of `anthropic` and `langchain_core`, and of `httpx2` in tests, weren't declared | **Fixed.** `anthropic>=1.17.0` and `langchain-core>=1.7.0` are runtime deps, and `httpx2>=2.16.0` is in the dev group. `langchain` stays deliberately: the brief asked for it, and workstream K uses `create_agent` |
| 9 | The PROMPT_VERSION and cache-prefix tests passed trivially | **Fixed.** `test_prompt_changes_bump_prompt_version` pins a sha256 over the system text, both tool variants and a rendered item message for each `PROMPT_VERSION`, so a prompt edit fails until the version is bumped. `test_system_prefix_and_tools_identical_across_items` runs `review_copy` on two different items and compares the system message and bound tools |

## Nits

| # | Finding | Resolution |
|---|---|---|
| 10 | "If there's no disclosure at all, quote the endorsing claim" is unreachable, because the span-less code finding drops it. "Not sponsored" silences the code regex | **Fixed.** The guidance now says to skip the rule when code findings already report a missing disclosure. The contradiction case ("not sponsored") stays, since it's exactly what code misses |
| 11 | The guidance asserted "This content is published by a partner" in the shared catalog | **Fixed.** It now reads "Applies only to content published by a partner…" |
| 12 | Code-finding quotes (copy excerpts) sit outside the data tag. The "can't forge" claim overstates 48 bits | **Fixed.** The system prompt says code-finding quotes are data too, and the docstring now calls it a costly search, not impossible |
| 13 | Same-rule findings on overlapping spans were both kept | **Fixed.** Same-rule overlap is now `DUPLICATE` (`test_overlapping_same_rule_finding_is_a_duplicate`). Run-to-run quote variance weakening ruling 4's carry-forward is noted for phase 2 in the report |
| 14 | `test_code_findings_unaffected_by_the_llm_step` can't fail | **Kept as documentation.** The real invariants are the schema/field-name walk and the obeying-model test, and the report says so |
| 15 | A missing API key raises `TypeError` from langchain-anthropic, not `LlmUnavailable`. Worst-case latency is ~4×60 s | **Documented** for phase 2: treat it as a config error at startup, and set the Celery time limit above ~5 min |
| 16 | The dead `span is None` sort branch | **Fixed** by the screen refactor (it sorts on the anchor span) |
| 17 | The cost line uses Haiku rates whatever `--model` is; scoring is presence-only | **Partly.** The cost label says "Haiku 5.5 rates for any model". Quote-level scoring is deferred and noted in the report |
| 18 | The report said "each has a primary source" while `pressure_tactics` is statute-only | **Fixed** in the report wording |
| 19 | `to_finding` maps any non-code kind to HUMAN | **Not changed.** `engine/rule.py` is outside this workstream's ownership. Flagged in the report for C/orchestrator |
| 20 | The report has placeholders and is untracked | **Fixed.** Filled with the final verification output and committed |

## Reviewer's verification gap

The live smoke test and the live eval were not run. The key is only in the repo-root `.env` pipe, which this
unattended run must not read. Forced tool choice on Haiku 5.5, cache engagement and prompt quality are verified
offline (payload construction, docs) but unproven against the API. The orchestrator runs:

```
cd backend
ANTHROPIC_API_KEY=... uv run python -m checks.llm.eval --repeat 3
ANTHROPIC_API_KEY=... CLEARPATH_ENV_FILE="" DJANGO_SECRET_KEY=t POSTGRES_PASSWORD=x uv run pytest -m live checks/llm
```
