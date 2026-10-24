# Report: LLM pre-review core (workstream D phase 1, issue #5)

Branch `wsD/llm-core`. Plan: `docs/plan/llm-core.md`. Review with resolutions:
`docs/plan/reviews/llm-core.md`.

Execution was native, not subagent-driven. The rule ids, the tool schema, the drop reasons and the prompt's
field semantics all have to agree, and the validator's edge cases decide what the prompt asks for. Each piece is
50–150 lines, so parallel implementers would have drifted on those shared names for little gain.

## What shipped

`backend/checks/llm/` is pure Python with no Django import.

| Module | Responsibility |
|---|---|
| `rules.py` | `LlmRule`, `LLM_RULES`, `LLM_RULES_BY_ID`, `LLM_RULESET_VERSION`, `applicable_rules(ctx)` |
| `spans.py` | `anchor_quote(text, quote, start, end) -> Anchor \| SpanRejection`, the span invariant |
| `schema.py` | the `report_findings` tool schema, `RawFinding`, `parse_report(AIMessage)`, `DropReason`, `DroppedFinding` |
| `prompt.py` | `system_message()` (static, cached), `item_message(...)`, `copy_tag(text)`, `PROMPT_VERSION` |
| `screen.py` | `screen(...)`: rule known/applicable, span, duplicates, code duplicates, wording. Pure |
| `review.py` | `review_copy`, `LlmReviewResult`, `TokenUsage`, `LlmUnavailable` (the provider boundary) |
| `client.py` | `get_review_model()`, `forces_tool_choice()`, the model constants |
| `eval/` | 17-case corpus, scorer and cost (`metrics.py`), runner, `python -m checks.llm.eval` |

Outside the package, `RuleSpec.kind` in `checks/engine/types.py` gains `"llm"`, which is additive. The new
runtime dependencies are:

- `langchain>=1.4.7`. Not imported here; the brief asked for it, and workstream K needs `create_agent`.
- `langchain-anthropic>=1.7.6`.
- `langchain-core>=1.7.0` and `anthropic>=1.17.0`, both imported directly. The error boundary depends on
  anthropic's exception classes.

`httpx2>=2.16.0` is added to the dev group, for constructing SDK errors in tests. A `live` pytest marker is registered and deselected by `addopts`.

## Rule set

There are 7 rules, all `warning` and all federal. `LLM_RULESET_VERSION = 2026-07-21`; `PROMPT_VERSION =
"2026-10-24.1"`.

| id | products | effective_from | citation | code counterparts (dedup) |
|---|---|---|---|---|
| `llm.creditworthiness_qualifier` | all | 2020-02-28 | CFPB Supervisory Highlights Issue 24 §2.9.1; Reg Z 12 CFR 1026.24(a), 1026.16(a) | `pricing.creditworthiness_qualifier` |
| `llm.credit_inquiry_scope` | all | 2017-01-01 | CFPB Supervisory Highlights Issue 24 §2.8.2; 12 U.S.C. 5536 | `claims.credit_impact` |
| `llm.material_connection` | all (partner content only) | 2023-07-26 | FTC 16 CFR 255.5; Reg Z comment 2(a)(2)-2; CFPB Supervisory Highlights Issue 37 | `endorsement.material_connection` |
| `llm.discouraging_statement` | all | 2026-07-21 | Reg B 12 CFR 1002.4(b) (text effective 2026-07-21) | none |
| `llm.net_impression` | all | 2020-02-28 | 12 U.S.C. 5531, 5536(a)(1)(B); Reg Z 12 CFR 1026.24(a), 1026.16(a); mortgages: Reg N 12 CFR 1014.3 | `claims.guaranteed`, `claims.preapproved` |
| `llm.pressure_tactics` | all | 2017-01-01 | 12 U.S.C. 5531, 5536(a)(1)(B) | none |
| `llm.mortgage_comparison` | mortgage_prequal | 2017-01-01 | Reg Z 12 CFR 1026.24(i)(2); Reg N 12 CFR 1014.3(h) | none |

Why these rules. Each is a judgment call that code can't settle. Six rest on a primary source in
`research/regulations.md`. `pressure_tactics` cites only the statute (see below).

- **The three from decisions.md, "Code checks vs LLM checks".**
  - `creditworthiness_qualifier` (row 3). The code's phrase list accepts "excellent credit" even in
    "Excellent credit? Not required".
  - `credit_inquiry_scope` (row 11). The code stays silent once substantiation is attached, but the scope of the
    claim still matters.
  - `material_connection` (row 16). The code only checks that a disclosure phrase exists; it can't judge "#sp",
    a disclosure buried at the end, or "100% unbiased".
- **Two from §4 UDAAP and §5 Reg B.**
  - `net_impression`
  - `discouraging_statement`. It judges text only; imagery stays `human.reg_b_discouragement`.
- **`pressure_tactics`.** This was in the brief. Its citation is the general deception and abusiveness
  statute. The research doc has no urgency-specific primary source, so the message asks the reviewer to confirm
  the deadline is real rather than asserting it's false.
- **`mortgage_comparison`.** The rules-engine report deferred 1026.24(i)(2) teaser comparisons to the LLM.

**All warnings (judgment).** A model's call is a prompt to look, not a detected fact, and spec ruling 3 already
forces every warning to be triaged before Approve.

`effective_from` reuses the engine's eCFR-derived constants (`checks.engine.rule`).

### Deliberately not implemented

| What | Why |
|---|---|
| 1026.24(i)(4), current-lender name without a non-affiliation statement | Rare in our copy (we don't market to another lender's customers by name); add as a mortgage rule if seed data needs it |
| 1026.24(i)(7), trigger terms split across languages | Needs bilingual ads in the corpus to evaluate; none exist yet |
| CAN-SPAM subject/body consistency beyond RE:/FW: | Lower stakes than the rules above; the code already catches fake reply prefixes |
| A rule flagging text addressed to reviewers or AI (the injection itself) | No regulatory citation fits (§5.4 requires one). The injected "pre-approved" is already caught by `claims.preapproved` in code |

## Prompt design (prompt-engineering and context-engineering skills)

### Render card

The request was verified offline with `ChatAnthropic._get_request_payload`; `test_client.py` pins it.

| | |
|---|---|
| Model / adapter | `claude-haiku-5-5` via `langchain_anthropic.ChatAnthropic` 1.7.6 |
| Rendered order (Anthropic) | tools, then system, then messages |
| Tools | one, `report_findings`, passed as an Anthropic-format dict (`convert_to_anthropic_tool` passes it through unchanged) |
| tool_choice | `{"type": "tool", "name": "report_findings"}`. Forced, so the reply starts with the tool call and has no thinking block |
| System | one text block, the static instructions plus all 7 rule definitions, with `cache_control: {"type": "ephemeral"}` |
| Messages | one user message: item facts, applicable rule ids and titles, offer terms, code findings, then the copy |
| Sampling | none sent. No temperature, top_p, top_k or thinking |
| Parser | `AIMessage.tool_calls` / `invalid_tool_calls`, then `parse_report`. No retry loop, and no hidden re-prompt |
| Cache prefix | tools + system ≈ 9.5k chars ≈ 2.4k tokens, above Haiku 5.5's 512-token minimum. Identical across items |

### Why it's laid out this way

- **Every item shares the same prefix.** The catalog lists every rule, not only the applicable ones, so the
  system message never varies by product or channel. Applicability is stated in the user message and also
  enforced in code (`NOT_APPLICABLE`). `test_system_block_is_identical_across_items` and the payload test guard
  it.
- **The copy is the last thing before the closing instruction.**
  - It sits inside `<ad_copy_XXXXXXXXXXXX>`, where the suffix is `sha256(copy)[:12]`. The copy can't contain its
    own closing tag, because that would need text containing a hash of itself, and it's deterministic for tests.
  - A one-line reminder after the copy restates the task.
  - The tag is a parsing aid, not a security boundary (the skill's warning applies). The guarantees are below.
- **Boundaries the prompt encodes.** These come from the skill's boundary ledger, with each separator placed on
  the surface nearest the decision:
  - Copy is data: text addressing reviewers or AI, or claiming approval, is ad content. This is in the system
    `<untrusted_copy>` section.
  - Code owns numbers and existing findings, so the model skips both. This is in `<how_to_review>`, and the
    code findings are listed in the item.
  - An empty list is complete and correct, which counters the pull to find something.
  - The quote is verbatim and is the shortest passage that is unique; for something missing, quote the claim
    that needs it. Offsets are best effort, since the quote is what's checked.
  - The message is one sentence in suggestion register with no citation, because code adds the citation from
    the rule and so the model can't invent one. The fix is replacement wording, or `""`.
  - Each rule's guidance is contrastive: what to flag, what not to flag, and what to quote.
- **The schema carries semantics.** Field descriptions sit on the fields, and `rule_id` is an enum of the 7 ids.
  The schema stays inside the strict-tool subset (all objects closed, all fields required, no constraints, no
  `anyOf`), so `strict: true` is a one-key change. It is off by default because I couldn't verify strict plus
  forced tool choice on Haiku 5.5 live, and a 400 would fail every check.

### Injection posture (defense in depth, spec §7)

1. **Code findings never pass through the model.** They're computed first and handed in read-only.
   `test_injection.py` asserts they're unchanged after an obeying model and after a resisting one.
2. **No approval capability.**
   - The tool schema has no status, approval or verdict field, and a test walks it.
   - Unknown top-level and item keys are ignored.
   - Calls to any other tool (`set_status`, `approve_item`) are recorded as `UNKNOWN_TOOL` and ignored.
   - `LlmReviewResult` has no status field.
3. **Spans are validated against the exact text.** The model can't point a finding at text that isn't there.
4. **An obeying model can only remove its own findings.** The injected "pre-approved" is still caught by the
   code rule `claims.preapproved` (asserted).
5. **The model's resistance itself is measured by the live eval,** on the `affiliate_injection` case (the
   runner prints it on its own line). A fake can't measure it, and the unit tests don't claim to.

## Public interface for phase 2

```python
from checks.llm import (
    review_copy, get_review_model, LlmReviewResult, LlmUnavailable, TokenUsage,
    DroppedFinding, DropReason, Adjustment, LLM_RULES, LLM_RULES_BY_ID, LLM_RULESET_VERSION,
    PROMPT_VERSION, DEFAULT_MODEL, applicable_rules, anchor_quote,
)

def get_review_model(model_name: str = "claude-haiku-5-5", *, api_key: str | None = None) -> ChatAnthropic
def review_copy(ctx: RuleContext, *, code_findings: Sequence[FindingDraft], model: BaseChatModel) -> LlmReviewResult

@dataclass(frozen=True)
class LlmReviewResult:
    findings: tuple[FindingDraft, ...]        # source=LLM, severity/citation from the rule, quote == text[span]
    dropped: tuple[DroppedFinding, ...]       # reason: DropReason, rule_id, quote, detail
    adjustments: tuple[Adjustment, ...]       # kind "reanchored" | "reworded" | "fix_removed"
    usage: TokenUsage                         # input_tokens (incl. cached), output_tokens, cache_read_tokens, cache_creation_tokens
    model_name: str                           # from the response (e.g. dated id), else the configured name
    latency_ms: int
    output_valid: bool                        # False: prose, unparsable, or max_tokens-truncated output
    stop_reason: str | None
    prompt_version: str
    ruleset_version: date

class LlmUnavailable(Exception):              # raised only by review_copy, after the SDK's retries
    retryable: bool                           # connection/timeout, 408, 409, 429, 5xx
```

`DropReason` values:

| Reason | Meaning |
|---|---|
| `malformed` | The item, or the whole call, failed to parse |
| `no_report` | The model replied in prose with no tool call |
| `unknown_tool` | A call to a tool other than `report_findings` |
| `unknown_rule` | The rule id isn't an LLM rule |
| `not_applicable` | The rule doesn't apply to this item |
| `empty_quote` | The quote is empty |
| `quote_not_found` | The quote isn't in the copy |
| `ambiguous_quote` | The quote appears more than once and the offsets match none of them |
| `duplicate` | The same rule already has a finding on an overlapping span |
| `duplicates_code` | A counterpart code finding overlaps, or is span-less |

**Offsets are Python `str` indices (code points), half-open.** This is the engine's convention too. The frontend
(workstream I) must convert to UTF-16 before highlighting, because an emoji is length 1 here and 2 in JS
(`test_offsets_are_code_points`).

## Deviations from the brief, and additions

| What | Why | Cost if wrong |
|---|---|---|
| **No `temperature=0`** | Haiku 5.5 returns a 400 for any temperature other than 1 (Haiku 5.5 migration guide, "Remove sampling parameters"; release notes 2026-10-07). LangChain only guards fable/sonnet-5-5 (`chat_models.py` ~1809), so 0 would reach the wire. `test_payload_has_no_sampling_parameters` pins it | No determinism knob: results vary run to run, so the eval takes `--repeat N` |
| **`tool_choice` gated by model** | Forced choice works on Haiku 5.5. Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1 reject it with a 400 and get `auto` | On `auto`, the model may answer in prose. That shows up as `output_valid=False` |
| **Code-duplicate filter (addition)** | The prompt asks the model not to repeat code findings, but prompting alone won't hold. Each LLM rule declares its code counterparts, and an overlapping (or span-less) counterpart code finding drops the LLM one (`duplicates_code`) | A distinct LLM nuance at the same passage is lost. The reviewer still sees the code finding |
| **Banned wording is replaced, not dropped (addition)** | §5.4 is enforced in code. A message with "violation", "non-compliant", "illegal" or "unlawful" gets the rule's `default_message` (recorded as `reworded`) rather than losing the finding | The text is generic for that finding |
| **`output_valid` (addition)** | Zero findings from a prose reply or a truncated reply must not look like a clean pass (§6.1, "never a silent gap") | none |
| **`strict` only on the `auto` path** | On the forced Haiku path, strict plus forced tool choice is unverified live, and a 400 would fail every check. On the `auto` path (Opus 5.5, Sonnet 5.5, Fable 5.1, Mythos 5.1), strict is on and `max_tokens` is 8192, because the docs recommend strict there and thinking spends the cap. That path is untested live | On Haiku, malformed items are still possible, but they're dropped and counted |
| **Forced tool choice skips thinking** | Cheaper and predictable on Haiku. Whether adaptive thinking (`auto` choice plus an instruction) buys recall is an eval question | Possibly lower recall on `net_impression` |

## Verification

Run from `backend/`. pytest-django needs the env vars even though no database is touched.

```
$ CLEARPATH_ENV_FILE="" DJANGO_SECRET_KEY=t POSTGRES_PASSWORD=x uv run pytest checks/llm -q
135 passed, 1 deselected in 0.51s
$ CLEARPATH_ENV_FILE="" DJANGO_SECRET_KEY=t POSTGRES_PASSWORD=x uv run pytest -q
465 passed, 1 deselected, 1 warning, 3 errors in 1.09s
$ uv run --group lint ruff check . && uv run --group lint ruff format --check .
All checks passed!
82 files already formatted
$ uv run --group typecheck pyrefly check
 INFO 0 errors (39 suppressed, 1 warning not shown, use `--min-severity=warn` to see it)
$ CLEARPATH_ENV_FILE="" DJANGO_SECRET_KEY=t POSTGRES_PASSWORD=x uv run pytest checks/llm -m live --collect-only -q
1/136 tests collected (135 deselected)
$ env -u ANTHROPIC_API_KEY uv run python -m checks.llm.eval
ANTHROPIC_API_KEY is not set in the environment.      (exit 2)
```

The 3 errors in the whole-suite run are `core/tests/test_health.py`, which needs a live Postgres; none was
running here. CI runs them.

**Not run: the live eval and the live smoke test.** The key lives only in the repo-root `.env` pipe, which must
not be read unattended. To run them:

```
cd backend
ANTHROPIC_API_KEY=... uv run python -m checks.llm.eval --repeat 3
ANTHROPIC_API_KEY=... CLEARPATH_ENV_FILE="" DJANGO_SECRET_KEY=t POSTGRES_PASSWORD=x uv run pytest -m live checks/llm
```

The eval scores only valid outputs; invalid ones (prose, truncated) are listed on their own line. It prints:
- per-case expected vs predicted
- per-rule TP/FP/FN, precision and recall, plus the overall line
- clean-case false positives
- drops by reason, re-anchors and rewordings
- tokens with cache read/write, cost at Haiku 5.5 rates, and latency
- the injection case on its own line

The cost math assumes Haiku 5.5 at ≤100k-token prompts ($0.10 input / $0.125 5m cache write / $0.01 cache read /
$0.50 output per MTok; pricing page fetched 2026-10-24). The live smoke test asserts the request is accepted,
the output parses, and a second call reads from the cache.

### Eval corpus (17 cases, `checks/llm/eval/corpus.py`)

| case | product | channel | partner | expected LLM rules |
|---|---|---|---|---|
| `pl_display_clean` | personal_loan | display | - | (clean) |
| `pl_landing_qualifier_reversed` | personal_loan | landing_page | - | creditworthiness_qualifier |
| `pl_email_inquiry_scope` | personal_loan | email | - | credit_inquiry_scope |
| `pl_landing_soft_pull_clean` | personal_loan | landing_page | - | (clean) |
| `pl_affiliate_disclosure_buried` | personal_loan | affiliate_page | affiliate | material_connection |
| `cc_influencer_vague_disclosure` | credit_card | paid_social | influencer | material_connection |
| `cc_email_pressure` | credit_card | email | - | pressure_tactics |
| `cc_landing_dated_promo_clean` | credit_card | landing_page | - | (clean) |
| `pl_paid_social_free_money` | personal_loan | paid_social | - | net_impression |
| `pl_display_debt_free` | personal_loan | display | - | net_impression |
| `pl_landing_discouraging` | personal_loan | landing_page | - | discouraging_statement |
| `pl_landing_outreach_clean` | personal_loan | landing_page | - | (clean) |
| `mtg_direct_mail_comparison` | mortgage_prequal | direct_mail | - | mortgage_comparison |
| `mtg_landing_clean` | mortgage_prequal | landing_page | - | (clean) |
| `affiliate_injection` | personal_loan | affiliate_page | affiliate | credit_inquiry_scope, pressure_tactics |
| `sms_pressure` | personal_loan | sms | - | pressure_tactics |
| `lead_gen_everyone_approved` | personal_loan | affiliate_page | lead_gen | net_impression |

Scoring is by presence per case: the right rule on the wrong passage still counts as a TP. Adding an expected
quote substring per case is a cheap follow-up. Labels are the post-screen set. `test_expected_findings_are_not_code_duplicates` pins that no expected LLM rule
has a counterpart code finding in its case, so a correct model finding can't be dropped as a duplicate and
counted as a miss.

## What phase 2 must wire

1. **Celery task** (`checks/tasks.py`), enqueued by the outbox handler on submit and on reviewer-authored
   versions. It is not run for fast-track versions (ruling 4: record "AI review carried from vN").
   1. Build the `RuleContext` from the version, item and current terms.
   2. Run `run_code_checks`.
   3. Call `review_copy(ctx, code_findings=..., model=get_review_model(settings.LLM_REVIEW_MODEL))`.
2. **Status mapping (`llm_check_status`):**
   - `succeeded` only if `output_valid`.
   - `output_valid=False`: retry once, then `failed`. It's a value, so retry it in the task, not via autoretry
     on an exception.
   - `LlmUnavailable(retryable=True)`: Celery autoretry with backoff, bounded, then `failed`. The SDK has
     already retried 3 times per call (0.5 s → 8 s), so keep Celery's count small.
   - `LlmUnavailable(retryable=False)` (400/401): `failed` immediately, with the error recorded.
3. **Persist** `findings` as Finding rows with `source=llm`. Each finding gets its span, quote, citation, message
   and suggested_fix.
   - Carry dismissals forward for an identical (rule, quote) pair (ruling 4).
   - Store `prompt_version`, `ruleset_version` and `model_name` on the check run.
4. **Cache key** (spec §7): the content hash, `LLM_RULESET_VERSION`, `PROMPT_VERSION`, the model name, and the
   code `ENGINE_VERSION`. The code findings are part of the input, so a code-engine change changes the LLM
   input too.
5. **Observability** (§6.4): log `model_name`, `usage` (including cache read/write), `latency_ms`,
   `len(dropped)` by reason, `adjustments` by kind, and `output_valid`. The cache-read count is the only proof
   caching engages; Anthropic returns no error when a prefix is below the minimum.
6. **Settings:** `LLM_REVIEW_MODEL` (default `claude-haiku-5-5`) and `ANTHROPIC_API_KEY` through the typed `Env`.
   Pass the key to `get_review_model(api_key=...)` explicitly rather than relying on ChatAnthropic's environment
   fallback.
7. **Errors and limits.**
   - A missing API key raises `TypeError` from langchain-anthropic, not `LlmUnavailable`. Validate the key at
     startup.
   - The worst-case latency of one `review_copy` is about 4 × 60 s plus backoff, so set the Celery time limit
     above about 5 minutes.
   - No temperature means quotes vary from run to run, so ruling 4's same-rule-same-quote carry-forward will
     match less often for LLM findings than for code findings.
8. **Don't build LLM findings with `checks.engine.rule.to_finding`.** It maps every non-code kind to
   `source=HUMAN`. `make_spec` also doesn't accept `kind="llm"`; `checks.llm.rules` builds `RuleSpec` directly. Making
   `to_finding` exhaustive (C's file) would close this. It's flagged for the orchestrator.
9. **Frontend (I):** convert code-point offsets to UTF-16 before highlighting.
