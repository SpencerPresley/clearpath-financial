# Review: rules engine (workstream C)

**What was reviewed.** One fresh reviewer subagent read `git diff main...HEAD` at `2500113` against:
- spec §4.2, §5.4, §6, §7
- the regs table in `research/regulations.md`
- decisions.md "Company facts"
- the interface contract

It probed the engine with its own ad copy, using scripts in the session scratchpad.

**Resolution status.** The fixes are in `a5757a1` plus one follow-up. Every reproduced bug now has a
regression test, named for its finding id, in `backend/checks/engine/tests/test_review_regressions.py`. All of
those tests failed before the fix. Re-running the reviewer's probe scripts afterwards gave the expected output
for every case.

## Findings and resolutions

| Id | Sev | Finding (short) | Resolution |
|---|---|---|---|
| H1 | high | Two examples in one paragraph swapped parts. `_nearest` used a 260-char window with no binding to the payment. `$337` was paired with $20,000 and 60 months and flagged as "$703". Fast-track wrote $703 into the copy and the re-check agreed with it. | **Fixed.** Each part now binds to its own payment: the nearest one before it (after any earlier payment), otherwise the nearest after it (before any later payment, same paragraph). This also covers a payment headline whose example follows in the next sentence ("Pay just $311/mo. Example: …"), found while re-probing. |
| H2 | high | "36 monthly payments of $337", the phrasing the engine itself suggests, was not recognized as an example. | **Fixed.** A payment count now counts as the example's term. |
| H3 | high | `card.deferred_interest` fired on a grace period, on a 0% intro APR described as "no interest", and on "If paid in full within 12 months, pay no interest". | **Fixed.** Grace-period wording is excluded (16(h)(2)). "No interest" in the same sentence as a 0% promotional APR is treated as a 16(g) intro rate (comment 16(h)-1). The order check runs over the whole sentence: "if paid in full" must come before the period, wherever the trigger sits. |
| H4 | high | `claims.preapproved` blocked common calls to action: "See what you qualify for", "how much you qualify for", "Once you qualify". | **Fixed.** "you qualify" after a question, condition or CTA word in the same clause is not treated as an assertion. |
| M1 | med | The negation lookback crossed commas, so "No paperwork, pre-approved in minutes" and "No fees, guaranteed approval" were missed. | **Fixed.** Negation must be in the same clause. |
| M2 | med | "for over 10 years" was read as a loan term. | **Fixed.** Tenure context ("for over", "trusted", "serving", …) before a duration marks it non-credit. |
| M3 | med | Several false positives: "save up to $200 a month" read as a payment, "Pay $0 in origination fees" as a payment, "2% lower" as a rate, "get $100" as a loan amount. | **Fixed.** Savings, bonus and referral dollars aren't terms. Named fees are classified before payments. Comparatives aren't rates. "get" was dropped from the amount cues. |
| M4 | med | Any card APR below `purchase_apr_min` was treated as an intro rate, which produced 5 wrong findings and an `intro_apr` ref. | **Fixed.** A card rate is promotional only if it has an intro or promo label, a stated period, or a value of 0. A low non-zero APR now gets the single correct `pricing.terms_available`. |
| M5 | med | "$0 annual fee for the first year, then $95" claimed $0 as the annual fee. | **Fixed.** The ongoing "$95" is claimed instead, and fast-track re-renders it. |
| M6 | med | Fast-track left a still-offered range end in place ("24 to 60" with new terms of 12–72), so the re-check warned. | **Fixed.** Range ends move to the new bounds, like APR min/max. A single stated length stays if it is still offered. Year-denominated terms remain non-refs, as reported; the re-check sends those items to the normal lane. |
| M7 | med | In "24, 36, 48, or 60 months" only 60 was detected. | **Fixed.** Every listed length is a term mention and is checked by `pricing.terms_available`. Listed lengths are deliberately not refs: re-rendering a list can produce duplicates ("36, 36, 48"). An offer change that removes a listed length blocks in the re-check instead. |
| L1 | low | A range produced two `creditworthiness_qualifier` findings. | **Fixed.** The high end of a range no longer inherits the qualifier. |
| L2 | low | Mid-sentence "no origination fee" re-renders clumsily ("Enjoy origination fee up to 4.75%"). | **Accepted, not fixed.** The text is accurate, and the fast-track diff shows it to the reviewer. Natural rewording needs grammar we don't have. |
| L3 | low | "One Market Plaza" and "4 Embarcadero Center" failed `email.postal_address`. | **Fixed.** Spelled-out building numbers and Center/Centre/Tower suffixes are accepted. |
| L4 | low | Disclaimers ("not affiliated with HUD or FHA") and referrals to a HUD-approved housing counselor were flagged. | **Fixed.** A negation in the same clause, or a housing-counseling referral, is skipped. |
| Legal 1 | — | `mortgage.arm_fixed` ignored 24(i)(1)(iii): an ad for both fixed and ARM products may use "fixed" for the fixed product. | **Fixed.** "fixed" that names a fixed-rate product ("30-year fixed", "fixed-rate mortgage") is excluded. |
| Legal 2 | — | Reg N 1014.3(q), which only covers mortgages, was the lead citation on personal-loan and card findings. | **Fixed.** Citations now lead with 12 U.S.C. 5536 and Reg Z 1026.24(a)/1026.16(a), with "mortgages: Reg N 1014.3(q)". |
| Legal 3 | — | `claims.guaranteed` ignores PRESCREEN_CRITERIA, and it matched rate guarantees. | **Rate guarantees fixed.** Only guarantees about approval or credit flag; "rate lock guarantee" and "rate is guaranteed for the life of the loan" don't. **Ignoring criteria is kept on purpose (judgment).** A prescreened firm offer can still be conditioned on verification and collateral (15 U.S.C. 1681a(l)), so "guaranteed" stays misleading even with criteria on file. |
| Interface 1 | — | Stale refs raised a bare `ValueError`. | **Fixed.** `StaleTermsRef(ValueError)` is exported, so F can catch it and route the item to the normal lane. |
| Interface 2 | — | Fast-track depends on the extractor version in use, because it re-analyzes the text to recover example parts and term roles. | **Accepted.** The contract persists only (field, span, value), so re-derivation is the only option. Any failure is now a typed `StaleTermsRef`, and `ENGINE_VERSION` lets callers see which extractor produced a ref. |
| Interface 3 | — | `human_checklist` takes no config. | **No change.** No human item is configurable. |
| Quality 1 | — | `RULESET_VERSION` only moves when the law changes, so check-result caches keyed on it would serve stale findings after a regex fix. | **Fixed.** `ENGINE_VERSION` is exported with a "bump on any behavior change" comment. Cache keys should include it (note for D/workstream 0). |
| Quality 2 | — | Rules with no versioned source used the adoption date 2026-10-24, so they dropped out silently for back-dated contexts. | **Fixed.** Those rules use the 2017-01-01 eCFR baseline, documented in `rule.py`. `RULESET_VERSION` is now 2026-07-21 (Reg B). A test pins that a context dated 2026-01-01 still gets the claims rules. |
| Quality 3 | — | Number classification is first-match-wins over windows of about 32 chars, which is fragile (judgment). | **Accepted, partly addressed.** Binding examples to their payment (H1/H2) removed the worst class of error. The rest is regex coverage, and the shouldn't-flag fixtures pin it. |
| Perf | — | 7 ms on dense copy, 45 ms on adversarial input. `_examples` is quadratic. | **Improved.** Bisect lookups, cached example extents, and a per-paragraph label cache. A payment-dense 5 KB adversarial input dropped from 40 ms to 8.7 ms. |

## Open questions the reviewer raised (for Spencer)

1. **Row 12 prescreen notices.**
   - Today: the engine has blocking code rules for the presence of the notices in the text (`prescreen.short_notice`, `prescreen.long_notice`), and the layout is the human item.
   - Conflict: ruling 7 calls row 12 a human checklist item. The workstream brief asked for "both notice headings" as a code check.
   - I kept both: code checks what's in the text, a human checks typography. Tell me if row 12 should be human-only.
2. **"Get pre-approved for a mortgage"** is treated as a call to action, not a 1014.3(q) representation, so it doesn't flag. If ClearPath only offers prequalification, inviting a "pre-approval" may misdescribe the product. That's a product and legal call. It's easy to make it a warning.
