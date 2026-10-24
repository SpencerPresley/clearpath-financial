# Spec builder check

Seven questions are left that I couldn't plan around without guessing, and a wrong guess would be expensive. They're ranked by how much of the plan each one moves. Everything else in the spec I could either decide myself or it's explicitly left to the builder.

One sequencing note that isn't a question: `samples/` doesn't exist yet. Workstream B is still running (ledger), so G can't be planned against `samples/README.md` until B lands.

---

## 1. How do offer-terms tokens actually work in submitted copy?

**Question.** Does `Version.content_text` store tokens (`{{PL_APR_FLOOR}}`) or the rendered text? Who puts the tokens in? Copy is "pasted or fetched from a URL" (spec.md:112-113), so affiliate copy arrives with literal "12.99% APR", not tokens. Does the system parse literals into `terms_refs`, or do only tokenized items "quote" terms? And what does a representative-example token carry, so that "$10,000 / 36 months / 12.99% APR = $337/mo" can be recomputed (decisions.md:92)?

**Why it changes the plan.** The token model is the differentiator (decisions.md:84-94). Five workstreams depend on it, and each would guess differently:
- **C**: does the rate check read a token or a parsed literal?
- **D**: LLM span offsets refer to one specific text, either the template or the rendered copy.
- **F**: which items count as "quoting v12" (product-spec.md:70), and so which ones can get a generated fast-track v+1 instead of a plain re-review.
- **I**: what the diff shows ("only the token changes", decisions.md:94).
- **G**: what the evidence pack exports as "the approved version."

There are three ways to build it:
- **Tokenized authoring.** The editor inserts tokens, and a version stores the template plus the rendered text.
- **Literal detection.** Rates are parsed out of plain text and mapped to terms fields.
- **A mix.** Tokens for first-party copy, detection for affiliate copy.

These differ in data model, editor, and check design. Related: `OfferTerms(apr_floor, apr_ceiling, fees{})` (product-spec.md:27) has nowhere to put card intro or go-to APRs, or a representative loan amount and term. Is that schema per product, or does it get extended?

## 2. What does "live" mean, and what happens to approved items that aren't live when terms change?

**Question.** The detailed docs contradict each other:
- decisions.md:85 says that when terms change, "every approved item still on the old version is flagged for re-review."
- product-spec.md:54 and :105, and spec.md:146-147, say only *live* items move to `needs_rereview`.

The spec's tiebreak rule, "the detailed doc wins" (spec.md:11), doesn't settle this, because both sides of the conflict are detailed docs.

The impact preview example, "14 approved items quote v12; 9 will need re-review" (product-spec.md:70), implies 5 items that aren't affected. What happens to them? Three options:
- They stay `approved` with stale rates.
- They get a v+1 without a status change.
- They go to `expired`, or some other state.

And how is "live" / "active placement" computed from `Placement(first_run, last_run, takedown_state?)` (product-spec.md:41-42)? Is it today within [first_run, last_run], with a null last_run meaning open-ended? Is a placement required before an item can be live, and who records it, the marketer after approval or the reviewer at approval?

**Why it changes the plan.** "Live" decides:
- the fan-out set in F
- the sweep branch in E (`needs_rereview` vs `expired`)
- queue priority ("re-reviews of live content first", spec.md:130)
- the "time to fix live content" metric

If approved-but-not-live items are left alone, one of them can go live quoting a superseded APR. That's the exact failure the feature exists to prevent. If placements are required for an item to count as live, the core-loop demo (spec.md:50-54, step 4) also needs seeded placements.

## 3. Which findings block which decisions?

**Question.** Four parts:
- **Severity.** spec.md:209 and :211 distinguish "non-blocking warning findings" from "blocking findings". But spec.md:134 and product-spec.md:104 block a decision while *any* finding is open, and neither `Finding` nor `Rule` has a severity field (product-spec.md:28, :35-36). Is there a severity, and do warnings block Approve?
- **Which decisions are gated.** spec.md:134 gates only Approve, but product-spec.md:104 gates every decision. Does Reject or Request changes require every finding to be triaged first?
- **Human checklist items** (spec.md:126). `Finding.source` is only `code | llm`. Are checklist items findings with `source=human`, and must the reviewer tick each one before Approve?
- **The LLM job.** Can a reviewer approve while `llm_check_status` is pending or `failed` (spec.md:294)?

**Why it changes the plan.** This is the audit invariant, not a UI detail. It sets:
- the `Finding` and `Rule` schema in workstream 0
- the decision service guard in E
- the red/amber treatment in H and I
- what a Decision record proves to an examiner. If unchecked human items don't block, the record can't show the Reg B imagery check was done.

## 4. Do generated and reviewer-authored versions get checked, and can their findings block a one-click approve?

**Question.** Approve-with-edits creates a reviewer-authored v+1 (spec.md:100-101). A terms change creates a generated fast-track v+1, approved "with one click" (decisions.md:94) and in bulk (decisions.md:138). Do code checks and the async LLM check run on those versions? If they flag something, does that block the one-click or bulk approve?

**Why it changes the plan.** Take the case decisions.md:97 itself raises: a new APR makes "lowest rate" false, and the code check flags it on the generated version. One of two things must give:
- **Findings block.** Bulk fast-track approval has to skip flagged items, and the fast-track lane needs a per-item fallback.
- **Findings don't block.** The "zero open findings" invariant has an exception, and that exception has to be written down for the audit trail.

Approve-with-edits has the same issue with the async LLM check: the reviewer either waits seconds before approving their own edit, or approves before the check finishes. This shapes the E/F service contracts and the I review-screen flow.

## 5. Are priority and risk tier one field or two, and who sets them?

**Question.** Three places use them:
- The queue sorts by "priority then age" (spec.md:130), and priority is edited inline (product-spec.md:66).
- Assignment weighs load by "risk tier: high 3, medium 2, low 1" (decisions.md:170).
- The legacy tracker has a "Risk Tier" column (research/market.md:44).

`ReviewItem` (product-spec.md:29-30) has neither field. Are they the same thing? Is risk tier derived (from product, channel, partner, trigger terms) or set by hand, and by whom: the marketer at intake, the reviewer, or the lead?

**Why it changes the plan.** It's a model field in workstream 0 and an input to E's assignment math. If risk tier is a free inline edit, anyone who can edit it can change reviewer load rankings, so the edit needs a permission rule and an event. If it's derived, it needs a rule table that nobody has specified.

## 6. What state does an item land in after it's pulled?

**Question.** `needs_rereview → pull (takedown)` (product-spec.md:56) is "tracked until confirmed down" (decisions.md:109), and `Placement.takedown_state?` exists. But the status machine (product-spec.md:51-57) has no state for the item once nothing is live. Where does it go:
- `expired`
- a new `withdrawn` / `pulled` state
- `changes_requested`, so the marketer can fix and resubmit
- or does it stay `needs_rereview` until the takedown is confirmed?

**Why it changes the plan.** E has to implement a transition the docs don't define. The answer also decides:
- the status enum and its color token (spec.md:204-212)
- whether a pulled item can come back through a new round
- where "time to fix live content" (product-spec.md:136) stops the clock: at pull request or at confirmed takedown

## 7. Do imported legacy items carry reviewable content, and which rule rows count as "applicable"?

Two smaller questions about scope.

**Legacy content.** The hosted DB is pre-seeded from the tracker (decisions.md:39-43), so legacy items are most of what evaluators see. The likely tracker columns are metadata plus "Asset Name / File Link" (research/market.md:44), with no copy text. If legacy items have no `content_text`, precedent search, the library, terms fan-out, and evidence packs are nearly empty on the demo. Are legacy items expected to hold copy, perhaps added at import or in seed data? Or are they metadata-only records that feed metrics and the archive list? Do they take part in the expiry sweep and terms re-review, or are they excluded? If they're included, the first sweep after seeding could flood the queue with `needs_rereview` / `expired` items.

**Applicable rules.** spec.md:120 turns "every applicable row" of the rule table (research/regulations.md:228-247) into a pure function. Several rows aren't text checks:
- **Row 12** (type size, placement): human-only per decisions.md:275.
- **Row 13** (NMLS): no verified California rule.
- **Row 14** (SMS consent record on file): depends on a record.
- **Row 17**: human.
- **Row 18** (retention): a workflow rule, not a check.

Rows 10 and 11 also depend on non-text facts: a "prescreen record" (product-spec.md:117) and evidence of the pull type. My proposed default:
- "Applicable" means text-checkable for California.
- Rows 12 and 17 become human checklist items.
- Row 13 is out.
- Rows 10, 11, and 14 check for an attachment of the right `kind` on the item.

Please confirm or correct. This sets C's scope and whether code rules take attachments as input as well as text.
