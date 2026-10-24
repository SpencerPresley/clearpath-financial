/*
 * UI-review screenshots of the walkthrough-1 review-screen and marketer fixes (spec §8.4). Skipped unless
 * SCREENSHOTS=1:
 *   SCREENSHOTS=1 npx playwright test e2e/screenshots-walkthrough-fixes.spec.ts
 * Output: docs/plan/reviews/ui/walkthrough-fixes/review/<finding>-<state>.png at 1440×900.
 */
import { expect, test } from '@playwright/test';
import type { Page, Route } from '@playwright/test';

import type {
  CheckPreviewIn,
  CheckPreviewOut,
  DecisionOut,
  FindingOut,
  ItemDriftOut,
  ItemHistoryOut,
  VersionSummaryOut,
} from '../src/api/generated/model';
import {
  ATTACHMENTS,
  DECISION_APPROVED,
  DECISION_CHANGES,
  FINDING_CREDIT,
  FINDING_QUALIFIER,
  FINDING_RATE,
  FINDINGS_OPEN,
  HISTORY,
  MARKETER,
  REVIEWER,
  dismissedAll,
  itemRowFixture,
  spanOf,
  triaged,
  versionFixture,
} from '../src/test/fixtures/review';
import { ME, queueRows, stubApi as stubQueue } from './api.ts';
import { stubApi } from './stubApi.ts';
import type { StubOptions } from './stubApi.ts';

const OUT = '../docs/plan/reviews/ui/walkthrough-fixes/review';

test.skip(process.env.SCREENSHOTS !== '1', 'set SCREENSHOTS=1 to capture UI-review screenshots');
test.use({ viewport: { width: 1440, height: 900 }, timezoneId: 'UTC' });

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

function summary(n: number, overrides: Partial<VersionSummaryOut> = {}): VersionSummaryOut {
  return {
    id: 500 + n,
    n,
    origin: 'submission',
    author: MARKETER,
    created_at: '2026-10-20T14:00:00Z',
    based_on_n: n === 1 ? null : n - 1,
    ...overrides,
  };
}

/** The fixture copy's one offer-terms quote (APR min, personal loan v12). */
const [PL_REF] = versionFixture(2).terms_refs;

const APPROVED_WITH_OVERRIDE: DecisionOut = {
  ...DECISION_APPROVED,
  engine_version: '2026-10-24.3',
  llm_override_reason: 'Provider outage; read the copy line by line.',
  terms_versions: [{ id: 12, product: 'personal_loan', version: 12 }],
};

const DRIFT: ItemDriftOut = {
  item_id: 1042,
  placements: [
    {
      placement_id: 3,
      location: 'LendCompare: best debt consolidation loans',
      url: 'https://lendcompare.example/best-debt-consolidation',
      monitored: true,
      is_live: true,
      failure_streak: 0,
      demo_page: null,
      latest: {
        id: 7,
        placement_id: 3,
        status: 'succeeded',
        trigger: 'scheduled',
        requested_by: null,
        requested_at: '2026-10-22T07:00:00Z',
        finished_at: '2026-10-22T07:00:05Z',
        url: 'https://lendcompare.example/best-debt-consolidation',
        final_url: 'https://lendcompare.example/best-debt-consolidation',
        http_status: 200,
        title: 'Best debt consolidation loans',
        compared_version_n: 2,
        result: 'modified',
        score: 88,
        diff: [
          {
            op: 'equal',
            text: 'Consolidate your debt with a ClearPath personal loan. Fixed rates as low as ',
          },
          { op: 'delete', text: '5.99%' },
          { op: 'insert', text: '7.99%' },
          { op: 'equal', text: ' APR (APRs 5.99%–35.99%). ' },
          { op: 'insert', text: 'Guaranteed approval for most applicants. ' },
          { op: 'equal', text: 'Checking your rate has no impact on your credit score. Terms 24–60 months.' },
        ],
        findings: [
          {
            rule_id: 'claims.guaranteed',
            citation: 'CFPB Supervisory Highlights Issue 24 §2.8.1',
            severity: 'blocking',
            message: 'Approval depends on underwriting, so a guarantee may mislead.',
            suggested_fix: '"Subject to credit approval."',
            quote: 'Guaranteed approval',
            new: true,
          },
        ],
        new_blocking_count: 1,
        error_code: null,
        error_message: null,
        reopened_item: true,
      },
    },
  ],
};

const HISTORY_WORDS: ItemHistoryOut = {
  entries: [
    ...HISTORY.entries,
    {
      id: 5,
      type: 'llm_check.started',
      actor: null,
      at: '2026-10-23T16:30:02Z',
      entity: 'version',
      entity_id: 502,
      from_status: null,
      to_status: null,
      payload: { check_run_id: 4, version_id: 502, attempt: 1 },
    },
    {
      id: 6,
      type: 'finding.accepted',
      actor: REVIEWER,
      at: '2026-10-24T09:00:00Z',
      entity: 'finding',
      entity_id: 9001,
      from_status: null,
      to_status: null,
      payload: { finding_id: 9001, rule_id: 'pricing.as_low_as_range', version_id: 502 },
    },
    {
      id: 7,
      type: 'finding.dismissed',
      actor: REVIEWER,
      at: '2026-10-24T09:01:00Z',
      entity: 'finding',
      entity_id: 9004,
      from_status: null,
      to_status: null,
      payload: {
        finding_id: 9004,
        rule_id: 'human.reg_b_discouragement',
        reason: 'Stock photo of a couple at a kitchen table; national targeting.',
        version_id: 502,
      },
    },
    {
      id: 8,
      type: 'item.risk_tier_overridden',
      actor: REVIEWER,
      at: '2026-10-24T09:02:00Z',
      entity: 'item',
      entity_id: 1042,
      from_status: null,
      to_status: null,
      payload: { before: 'medium', after: 'high' },
    },
    {
      id: 9,
      type: 'decision.recorded',
      actor: REVIEWER,
      at: '2026-10-24T10:00:00Z',
      entity: 'decision',
      entity_id: 802,
      from_status: 'in_review',
      to_status: 'approved',
      payload: {
        decision_id: 802,
        version_id: 502,
        outcome: 'approved',
        lane: 'standard',
        reason: APPROVED_WITH_OVERRIDE.reason,
        expires_at: APPROVED_WITH_OVERRIDE.expires_at,
      },
    },
  ],
};

/** Live checks with one literal fix (a figure) and one instruction, wherever "5.99%" stands alone. */
function literalPreview(body: CheckPreviewIn): CheckPreviewOut {
  const text = body.content_text;
  const findings = text.includes(' 5.99% APR')
    ? [
        {
          rule_id: 'pricing.terms_current',
          citation: 'Reg Z 12 CFR 1026.24(a)',
          source: 'code' as const,
          severity: 'blocking' as const,
          message: 'This APR isn’t offered; current APRs are 9.99%–35.99%.',
          suggested_fix: '9.99%',
          span: spanOf(text, '5.99%'),
          quote: '5.99%',
        },
      ]
    : [];
  return { ruleset_key: 'k', terms_refs: [], findings };
}

/** Needs re-review only: the queue stub answers this view with the rows given (not its board rows). */
const REREVIEW_VIEW = '/queue?view=rereview&status=%5B%22needs_rereview%22%5D&is_legacy=false';

/** One re-review, CP-1099, whose reopen reason is `reason`. */
function rereviewRows(reason: 'drift_detected' | 'approval_expired') {
  return queueRows()
    .filter((r) => r.status === 'needs_rereview')
    .slice(0, 1)
    .map((base) => ({
      ...base,
      id: 1099,
      key: 'CP-1099',
      title: 'LendCompare: best debt consolidation loans',
      reopen_reason: reason,
      channel: 'affiliate_page' as const,
      partner: { id: 11, name: 'LendCompare' },
    }));
}

interface Shot {
  name: string;
  path: string;
  stub?: StubOptions;
  /** Extra routes registered after the stub (they win). */
  routes?: (page: Page) => Promise<unknown>;
  queue?: Parameters<typeof stubQueue>[1];
  ready: (page: Page) => Promise<void>;
}

const heading = (page: Page) => expect(page.getByRole('heading', { level: 1 })).toBeVisible();

const shots: Shot[] = [
  {
    name: 'b4-fast-track-approved-ai-carried',
    path: '/items/1042',
    stub: {
      item: {
        status: 'approved',
        llm_check_status: 'skipped',
        current_version_n: 4,
        current_version: versionFixture(2, { id: 504, n: 4, origin: 'fast_track', based_on_n: 3 }),
        versions: [summary(1), summary(2), summary(3), summary(4, { origin: 'fast_track' })],
        latest_decision: {
          ...DECISION_APPROVED,
          version_n: 4,
          lane: 'fast_track',
          ai_review_carried_from_n: 3,
        },
      },
      findings: [],
    },
    ready: (page) => expect(page.getByText('AI review carried from v3')).toBeVisible(),
  },
  {
    name: 's3-s9-details-decision-record',
    path: '/items/1042?tab=details',
    stub: {
      item: {
        status: 'approved',
        risk_tier: 'high',
        latest_decision: APPROVED_WITH_OVERRIDE,
        current_version: versionFixture(2, {
          terms_refs: [
            ...versionFixture(2).terms_refs,
            { ...PL_REF, span: { start: 0, end: 1 } },
            {
              ...PL_REF,
              field: 'term_months',
              quote: '24',
              quoted_value: '24',
            },
            {
              ...PL_REF,
              field: 'term_months',
              quote: '60',
              quoted_value: '60',
            },
          ],
        }),
      },
      findings: dismissedAll(FINDINGS_OPEN),
    },
    ready: (page) => expect(page.getByRole('heading', { name: 'Decision record' })).toBeVisible(),
  },
  {
    name: 's3-s9-history-words-and-record',
    path: '/items/1042?tab=history',
    stub: {
      item: { status: 'approved', latest_decision: APPROVED_WITH_OVERRIDE },
      findings: dismissedAll(FINDINGS_OPEN),
      history: HISTORY_WORDS,
    },
    routes: (page) =>
      page.route('**/api/items/1042/decisions', (route) =>
        json(route, [APPROVED_WITH_OVERRIDE, DECISION_CHANGES]),
      ),
    ready: async (page) => {
      const toggles = page.locator('summary', { hasText: 'Decision record' });
      await expect(toggles.first()).toBeVisible();
      await toggles.first().click();
      await expect(page.getByText('Overridden: Provider outage; read the copy line by line.')).toBeVisible();
    },
  },
  {
    name: 's14-live-page-vs-approved-center',
    path: '/items/1042?live=true',
    stub: {
      item: {
        status: 'needs_rereview',
        reopen_reason: 'drift_detected',
        live_placements_count: 1,
        approved_at: '2026-10-01T10:00:00Z',
        latest_decision: DECISION_APPROVED,
        drift_rereview: { placement_id: 3, restored: false },
      },
      findings: [],
    },
    routes: (page) => page.route('**/api/items/1042/drift', (route) => json(route, DRIFT)),
    ready: (page) => expect(page.getByText(/Live page vs approved v2 · LendCompare/)).toBeVisible(),
  },
  {
    name: 's14-s5-nit14-details-check-metadata',
    path: '/items/1042?live=true&tab=details',
    stub: {
      item: {
        status: 'needs_rereview',
        reopen_reason: 'drift_detected',
        live_placements_count: 1,
        approved_at: '2026-10-01T10:00:00Z',
        latest_decision: DECISION_APPROVED,
        drift_rereview: { placement_id: 3, restored: false },
      },
      findings: [],
    },
    routes: (page) => page.route('**/api/items/1042/drift', (route) => json(route, DRIFT)),
    ready: (page) =>
      expect(page.getByRole('button', { name: 'Show live page vs approved v2' })).toBeVisible(),
  },
  {
    name: 's5-queue-drawer-live-copy-changed',
    path: `${REREVIEW_VIEW}&item=1099`,
    queue: { rows: rereviewRows('drift_detected') },
    ready: (page) => expect(page.getByText('Re-review: Live copy changed')).toBeVisible(),
  },
  {
    name: 's6-marketer-ai-not-configured',
    path: '/items/1042',
    stub: {
      roles: ['marketer'],
      item: {
        status: 'submitted',
        llm_check_status: 'failed',
        llm_check_failure_code: 'not_configured',
        llm_check_failure_reason: "The AI check didn't run: no Anthropic API key is configured here.",
      },
    },
    ready: (page) =>
      expect(
        page.getByText('AI pre-review didn’t run; your reviewer will check this by hand.'),
      ).toBeVisible(),
  },
  {
    name: 's6-marketer-ai-queued',
    path: '/items/1042',
    stub: { roles: ['marketer'], item: { status: 'submitted', llm_check_status: 'pending' } },
    ready: (page) => expect(page.getByText(/AI pre-review queued\./)).toBeVisible(),
  },
  {
    name: 's17-last-round-header',
    path: '/items/1042',
    stub: {
      roles: ['marketer'],
      item: { status: 'submitted', round: 2, latest_decision: DECISION_CHANGES },
    },
    ready: (page) => expect(page.getByText(/Last round: changes requested on v1/)).toBeVisible(),
  },
  {
    name: 's8-shortcuts-dialog',
    path: '/items/1042',
    ready: async (page) => {
      await heading(page);
      await page.keyboard.press('?');
      await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible();
    },
  },
  {
    name: 's8-shift-a-opens-approve-form',
    path: '/items/1042',
    stub: { findings: dismissedAll(FINDINGS_OPEN) },
    ready: async (page) => {
      await expect(page.getByRole('button', { name: 'Approve', exact: true })).toBeEnabled();
      await page.keyboard.press('Shift+A');
      await expect(page.getByLabel(/^Reason/)).toBeFocused();
    },
  },
  {
    name: 's8-after-decision-next-item-focused',
    path: '/items/1042',
    stub: { findings: dismissedAll(FINDINGS_OPEN) },
    ready: async (page) => {
      await expect(page.getByRole('button', { name: 'Approve', exact: true })).toBeEnabled();
      await page.keyboard.press('Shift+A');
      await page.getByLabel(/^Reason/).fill('Range and license line present; credit claim limited.');
      await page.keyboard.press('ControlOrMeta+Enter');
      await expect(page.getByRole('button', { name: 'Next item' })).toBeFocused();
    },
  },
  {
    name: 's11-approve-with-edits-apply',
    path: '/items/1042',
    stub: {
      // triaged() accepts the 1st and 3rd: the credit claim (a literal fix) must change.
      findings: triaged([
        { ...FINDING_CREDIT, suggested_fix: '"Checking your rate won’t affect your credit score."' },
        FINDING_QUALIFIER,
        FINDING_RATE,
      ] as FindingOut[]),
    },
    ready: async (page) => {
      await heading(page);
      await page.keyboard.press('e');
      await expect(page.getByLabel('Edited copy (v3)')).toBeVisible();
      await expect(page.getByRole('button', { name: /^Apply suggestion/ }).first()).toBeVisible();
    },
  },
  {
    name: 's11-nit6-resubmit-apply-once',
    path: '/mine/1042/resubmit',
    stub: {
      roles: ['marketer'],
      item: { status: 'changes_requested', latest_decision: { ...DECISION_CHANGES, version_n: 2 } },
      findings: [
        { ...FINDING_RATE, state: 'accepted', resolved_by: REVIEWER },
        { ...FINDING_QUALIFIER, state: 'accepted', resolved_by: REVIEWER },
      ],
    },
    routes: (page) =>
      page.route('**/api/checks/preview', (route) =>
        json(route, literalPreview(route.request().postDataJSON() as CheckPreviewIn)),
      ),
    ready: (page) => expect(page.getByRole('button', { name: 'Apply suggestion: 9.99%' })).toBeVisible(),
  },
  {
    name: 's11-new-submission-apply',
    path: '/submit',
    stub: { roles: ['marketer'] },
    routes: (page) =>
      page.route('**/api/checks/preview', (route) =>
        json(route, literalPreview(route.request().postDataJSON() as CheckPreviewIn)),
      ),
    ready: async (page) => {
      await page.getByLabel('Title').fill('Fall personal loan promo');
      await page.getByRole('button', { name: /Product/ }).click();
      await page.getByRole('option', { name: 'Personal loan' }).click();
      await page.getByRole('button', { name: /Channel/ }).click();
      await page.getByRole('option', { name: 'Paid social' }).click();
      await page.getByLabel('First run').fill('2026-11-01');
      await page
        .getByRole('textbox', { name: /copy/i })
        .first()
        .fill('Personal loans for home projects from 5.99% APR. Terms 24–60 months.');
      await expect(page.getByRole('button', { name: 'Apply suggestion: 9.99%' })).toBeVisible();
    },
  },
  {
    name: 'b3-new-round-terms-changed',
    path: '/mine/1042/resubmit',
    stub: {
      roles: ['marketer'],
      item: {
        status: 'expired',
        reopen_reason: 'terms_changed',
        round: 2,
        current_version_n: 3,
        current_version: versionFixture(2, {
          id: 503,
          n: 3,
          origin: 'fast_track',
          content_text: versionFixture(2).content_text.replace('5.99%', '9.99%'),
          terms_refs: [{ ...PL_REF, offer_terms: { id: 13, product: 'personal_loan', version: 2 } }],
        }),
        approval_expires_at: '2027-03-19T00:00:00Z',
        latest_decision: DECISION_APPROVED,
      },
      findings: [],
      history: {
        entries: [
          {
            id: 532,
            type: 'item.expired',
            actor: null,
            at: '2026-10-18T09:00:00Z',
            entity: 'item',
            entity_id: 1042,
            from_status: 'approved',
            to_status: 'expired',
            payload: { reason: 'terms_changed', offer_terms_id: 13, generated_version_id: 503 },
          },
        ],
      },
    },
    ready: (page) =>
      expect(page.getByText(/Expired Oct 18, 2026 when personal loan offer terms v2/)).toBeVisible(),
  },
  {
    name: 'nit15-waiting-on-you-order',
    path: '/mine',
    stub: {
      roles: ['marketer'],
      rows: [
        itemRowFixture({
          id: 1041,
          key: 'CP-1041',
          title: 'Affiliate page — LendCompare',
          status: 'withdrawn',
        }),
        itemRowFixture({
          id: 1040,
          key: 'CP-1040',
          title: 'Spring PL email',
          status: 'expired',
          reopen_reason: 'terms_changed',
        }),
        itemRowFixture({
          id: 1042,
          key: 'CP-1042',
          status: 'changes_requested',
          latest_decision: DECISION_CHANGES,
        }),
        itemRowFixture({
          id: 1043,
          key: 'CP-1043',
          title: 'Card launch',
          status: 'in_review',
          assignee: REVIEWER,
        }),
      ],
    },
    ready: (page) => expect(page.getByRole('region', { name: 'Waiting on you, 3 items' })).toBeVisible(),
  },
  {
    name: 'nit16-bulk-fast-track-off',
    path: REREVIEW_VIEW,
    queue: { me: ME.lead, rows: rereviewRows('approval_expired') },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      await page.getByRole('checkbox', { name: 'Select CP-1099' }).click();
      await page.getByRole('button', { name: 'Why fast-track is off' }).focus();
      await expect(page.getByRole('tooltip')).toBeVisible();
    },
  },
  {
    name: 'nit4-fast-track-reason-prefilled',
    path: '/items/1042',
    stub: {
      item: {
        status: 'needs_rereview',
        reopen_reason: 'terms_changed',
        llm_check_status: 'skipped',
        live_placements_count: 1,
        latest_decision: { ...DECISION_APPROVED, version_n: 1 },
        current_version: versionFixture(2, { origin: 'fast_track' }),
      },
      findings: [],
    },
    ready: async (page) => {
      await page.getByRole('button', { name: 'Fast-track approve v2' }).click();
      await expect(page.getByLabel(/^Reason/)).toHaveValue('Only the offer-terms numbers changed.');
    },
  },
  {
    name: 'nit5-provider-error-plain',
    path: '/items/1042',
    stub: {
      item: {
        llm_check_status: 'failed',
        llm_check_failure_code: 'provider_unavailable',
        llm_check_failure_reason:
          "The AI service didn't answer after 4 tries. The model provider returned 529.",
      },
      findings: dismissedAll(FINDINGS_OPEN),
    },
    ready: (page) => expect(page.getByText(/AI check failed: The AI service was overloaded/)).toBeVisible(),
  },
];

for (const shot of shots) {
  test(shot.name, async ({ page }) => {
    if (shot.queue !== undefined) {
      await stubQueue(page, shot.queue);
    } else {
      await stubApi(page, { attachments: ATTACHMENTS, ...shot.stub });
    }
    await shot.routes?.(page);
    await page.goto(shot.path);
    await shot.ready(page);
    await page.waitForTimeout(400); // let transitions settle
    await page.screenshot({ path: `${OUT}/${shot.name}.png` });
  });
}
