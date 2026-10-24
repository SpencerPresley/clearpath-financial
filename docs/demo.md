# ClearPath demo

The demo is a compliance team's first ten weeks on ClearPath at a consumer lender: 44 items across personal loans,
the ClearPath Card and mortgages, in every status, plus the 178 rows imported from the Excel tracker they used
until go-live (September 2025 to Friday 2026-08-14; the app's history starts the Monday after). Every row
was made by the real services on a backdated clock (`backend/demo/`), so history, findings, decisions,
comments, notifications and metrics are what the product itself would have recorded.

## Logins

Password for every account: on the hosted demo, the password you were given with the link (it's generated per
deployment; the published one below is refused there). Locally, `ClearPath-demo-2026` unless `DEMO_USER_PASSWORD` is set.

| Role | Email | Who |
|---|---|---|
| Reviewer | `reviewer@clearpath.demo` | Dana Kim |
| Compliance lead | `lead@clearpath.demo` | Rachel Okafor (also reviews) |
| Marketer | `marketer@clearpath.demo` | Priya Natarajan, performance marketing |
| Admin | `admin@clearpath.demo` | Avery Chen |

The rest of the team is seeded with the same password: reviewers Samuel Ortega (`sam@`), Leah Brandt (`leah@`, out
of office) and Nikhil Rao (`nikhil@`); marketers Marcus Bell (cards, `marcus@`), Elena Ruiz (mortgages, `elena@`),
Jordan Whitfield (partners, `jordan@`) and Hannah Cho (email and SMS, `hannah@`).

## Five minutes as each role

### Reviewer (Dana)

You land on **My queue**: five items, ordered by what to do first.

1. **CP-2, PL debt consolidation landing page** (needs re-review, offer terms changed). The rate sheet moved the
   floor APR, v4 was generated with the new numbers, and the AI review carried over because only the numbers
   changed. **Compare with approved v3** shows the diff; **Fast-track approve v4** clears it in one step.
2. **CP-40, FinMatch: prequal marketplace listing**. The AI check failed (the provider returned 529 four times).
   Two blocking code findings: a payment term with no payment amount, and "no impact to your credit score" without
   the soft-pull qualifier. Accept them and request changes, or try to approve and see that it needs an override
   reason because the AI never answered.
3. **CP-7, LendCompare listing** (needs re-review, drift). The drift monitor checks LendCompare's page every
   morning; two days ago it found the partner had lowered the starting APR to 7.99% and swapped "Subject to credit
   approval" for "Guaranteed approval for most applicants", the guarantee taken out in round 1. **Details** →
   *Where it runs* shows the check and its diff; Dana's comment asks Jordan to get the approved copy back. The page
   is one ClearPath hosts for the demo (`/demo-partners/lendcompare/`), so you can open it and see the edit.
   The decision bar offers **Check now** and **Pull**, not Reaffirm: the page still differs. (Playing the partner
   who fixes it takes a lead; see Rachel's drift bullet.)
4. **CP-26, Money with Maya: card payoff reel**. An influencer's second round: the "#ad" disclosure is fixed, and
   the AI flags a new urgency line ("Rates this low won't last") with a suggested rewrite.

Then open **Unassigned**: two submissions are waiting there because Leah went out of office and her queue was
released. CP-35 has waited more than three days.

### Compliance lead (Rachel)

Rachel's own queue has the high-stakes items she took on: **CP-31**, a card prescreen mailer that needs the
issuing bank's sign-off; **CP-37**, a rush refi postcard; and **CP-8**, a fast-track after the rate sheet. As lead
she can also:

- reassign anything (open any item, **Details**, assignee), and see **Unassigned** and **Waiting >3 days** across
  the team;
- open **Workload by reviewer** under the queue counts: each reviewer's open items and weighted load (high 3,
  medium 2, low 1), the number auto-assignment ranks by. Leah shows as out of office, and the assignee menus mark
  her too. A reviewer's open count opens exactly those items;
- review **Offer terms**: personal loan v1 (the 9.49% floor carried over from the tracker at go-live) and v2
  (today's 9.99%), and card v1 and v2 (the Prime move). Each publish fanned out to the approvals that quoted it,
  which is where the terms re-reviews come from;
- review **Partners**: ten partners (affiliate review sites and blogs, lead-gen shops, marketplaces, an
  influencer), each with its agreement attached;
- run the drift monitor live: open **CP-23, CardScout: ClearPath Card review** (approved, live on CardScout's
  page, last check unchanged), **Details** → *Where it runs* → **Simulate partner edit** (CardScout drops the offer)
  → **Check now**. The check comes back *missing* and the item returns to the queue as a re-review. **CP-32,
  BudgetBee** shows the opposite case: the partner redesigns the article but keeps the approved words, and the
  check stays *unchanged*. **Restore original page** puts a page back; **Reset demo** restores all three. To
  close **CP-7** the way the partner would: *Where it runs* → **Restore original page**, then **Check now**. The
  check comes back *unchanged*, **Reaffirm** appears in the decision bar, and reaffirming returns CP-7 to
  approved;
- check **Metrics**: ten weeks of submissions, findings and decisions behind them.

### Marketer (Priya)

You land on **My submissions**.

- **Waiting on you**: **CP-22** came back with changes requested. Samuel's note asks for the card issuer line,
  so **Resubmit** with it added. **CP-10** and **CP-11** expired, one after the rate change and one past its
  approval window, and **CP-13** was pulled from market. Each offers **Start new round**.
- **With compliance**: what reviewers have and who's on it.
- **New submission**: paste copy for any product and channel and watch the code checks and AI pre-review land.

### Admin (Avery)

You land on **Import**.

- **Import** shows the Excel tracker import that brought in the 178 legacy rows at go-live (matched to partners
  where the tracker named one). They're in the **Library** with `legacy=only`. Open it from **Recent imports**: its
  **Columns**, **Values** and **Preview** steps stay viewable, read-only, so you can see the mapping it inferred
  (`PL` as Personal loan, `CardPerks` matched to CardPerks Weekly) and what happened to each messy row ("Imported,
  date from last round", "Skipped: duplicate"). **Load sample tracker** walks the same steps on a new copy; since
  the rows are already in, its preview says so in one line and links back to that import.
- **Users**: everyone's roles, availability and account. Toggle a role, mark Leah back in office, add someone.
  There's always an admin: you can't deactivate yourself or drop the last admin role. Reviewers set their own
  availability from the account menu. **Metrics** is in an admin's nav too.
- **Reset demo**: account menu (top right), **Reset demo…**, confirm. It runs as a background job, takes about
  ten seconds, and everyone stays signed in. The dialog can be closed while it runs; a notice appears when it's
  done.

## What's scripted

- **AI findings** in the seed come from a scripted model (`demo-seed` on each check run), so every reset gives
  the same findings. New submissions after a reset use the deployment's real model.
- **CP-222** (Display banner: get ahead of holiday bills) is seeded with its AI check still pending. The AI
  reconciler picks it up ten minutes after a reset and runs it on the real model (or, with no API key
  configured, records the check as failed). Within the first ten minutes it shows the pending state.
- **Partner pages.** LendCompare, CardScout and BudgetBee are pages ClearPath hosts at `/demo-partners/` for
  the drift demo. A reset leaves LendCompare edited (so CP-7's re-review matches what a fresh check finds) and the
  other two original. The seeded checks were recorded on the same HTML those pages serve; **Check now** fetches
  them for real through the worker.
- Dates are relative to the moment of the reset, so "5 days ago" stays five days ago.

## Running it

```sh
cd backend
uv run python manage.py seed_demo          # no-op if items exist
uv run python manage.py seed_demo --reset  # wipe and reseed
```

Under `make up`, set `DEMO_PARTNERS_BASE_URL=http://web:8000` before the first boot: the worker container can't
reach the default (`FRONTEND_BASE_URL`), so **Check now** on the partner pages would fail, and the seeded
placements keep the address they were created with.

Containers seed on start: `compose.yaml`'s web service and `deploy/deploy.sh` run `seed_demo` after
`migrate`, which does nothing once items exist. `seed_demo` keeps user accounts and sessions; it wipes items,
partners, offer terms, imports, findings, drift checks, events and notifications. People are upserted from `backend/demo/content/people.py`, and the password changes only if it
differs, so existing sessions survive.
