/*
 * UI-review captures (spec §8.4), not assertions. Runs only with SCREENS=1:
 *   SCREENS=1 npx playwright test e2e/screens.spec.ts
 * Writes to docs/plan/reviews/ui/review/ at 1440x900 and 1280x800.
 */
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

import {
  DECISION_APPROVED,
  FINDINGS_OPEN,
  PLACEMENTS,
  itemRowFixture,
  triaged,
  versionFixture,
} from '../src/test/fixtures/review';
import { stubApi } from './stubApi';
import type { StubOptions } from './stubApi';

const OUT = '../docs/plan/reviews/ui/review';
const SIZES = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
] as const;

test.skip(!process.env.SCREENS, 'screenshots only with SCREENS=1');

async function capture(page: Page, name: string) {
  await page.evaluate(() => document.fonts.ready);
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.waitForTimeout(150);
    await page.screenshot({ path: `${OUT}/${name}-${String(size.width)}x${String(size.height)}.png` });
  }
}

const generated = versionFixture(2, {
  origin: 'fast_track',
  author: { id: 0, name: 'System' },
  content_text: versionFixture(1).content_text.replace('5.99%', '6.49%'),
});
const generatedVersions = [
  { ...versionFixture(1), terms_refs: undefined },
  {
    id: generated.id,
    n: 2,
    origin: 'fast_track' as const,
    author: generated.author,
    created_at: '2026-10-24T08:00:00Z',
    based_on_n: 1,
  },
].map(({ id, n, origin, author, created_at, based_on_n }) => ({
  id,
  n,
  origin,
  author,
  created_at,
  based_on_n,
}));

const REVIEW_STATES: Record<
  string,
  { url?: string; options: StubOptions; before?: (page: Page) => Promise<void> }
> = {
  'review-open-findings': {
    options: {},
    before: async (page) => {
      await page.keyboard.press('n');
    },
  },
  'review-all-triaged': {
    options: { findings: triaged(FINDINGS_OPEN) },
    before: async (page) => {
      await page.getByRole('button', { name: 'Approve', exact: true }).click();
      await page
        .getByLabel('Reason')
        .fill('Range and license line present; credit claim limited to the rate check.');
    },
  },
  'review-ai-pending': {
    options: {
      item: { llm_check_status: 'running' },
      findings: triaged(FINDINGS_OPEN).filter((f) => f.source !== 'llm'),
    },
  },
  'review-ai-failed': {
    options: {
      item: { llm_check_status: 'failed' },
      findings: triaged(FINDINGS_OPEN).filter((f) => f.source !== 'llm'),
    },
  },
  'review-approved': {
    options: {
      item: {
        status: 'approved',
        latest_decision: DECISION_APPROVED,
        approved_at: DECISION_APPROVED.decided_at,
        approval_expires_at: DECISION_APPROVED.expires_at,
        live_placements_count: 1,
      },
      findings: triaged(FINDINGS_OPEN),
    },
    url: '/items/1042?tab=history',
  },
  'review-needs-rereview': {
    options: {
      item: {
        status: 'needs_rereview',
        reopen_reason: 'terms_changed',
        llm_check_status: 'skipped',
        live_placements_count: 1,
        latest_decision: { ...DECISION_APPROVED, version_n: 1 },
        current_version: generated,
        versions: generatedVersions,
      },
      findings: [],
    },
    url: '/items/1042?compare=1',
  },
  'review-withdrawn': {
    options: {
      item: { status: 'withdrawn', latest_decision: DECISION_APPROVED },
      findings: triaged(FINDINGS_OPEN),
      placements: [
        {
          ...PLACEMENTS[0],
          is_live: false,
          takedown_state: 'confirmed',
          takedown_requested_at: '2026-10-24T13:00:00Z',
          takedown_confirmed_at: '2026-10-24T14:00:00Z',
        },
      ],
    },
  },
  'review-compare': { options: {}, url: '/items/1042?v=2&compare=1' },
  'review-edit': {
    options: { findings: triaged(FINDINGS_OPEN) },
    before: async (page) => {
      await page.keyboard.press('e');
    },
  },
};

for (const [name, state] of Object.entries(REVIEW_STATES)) {
  test(name, async ({ page }) => {
    await stubApi(page, state.options);
    await page.goto(state.url ?? '/items/1042');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await state.before?.(page);
    await capture(page, name);
  });
}

test('intake-empty', async ({ page }) => {
  await stubApi(page);
  await page.goto('/submit');
  await capture(page, 'intake-empty');
});

test('intake-live-findings', async ({ page }) => {
  await stubApi(page);
  await page.goto('/submit');
  const copy = page.getByRole('textbox', { name: /copy/i }).first();
  await copy.fill(versionFixture(1).content_text + '\nGuaranteed approval in minutes.');
  await page.waitForTimeout(600);
  await capture(page, 'intake-live-findings');
});

test('mine', async ({ page }) => {
  await stubApi(page, {
    rows: [
      itemRowFixture({ id: 1042, key: 'CP-1042', status: 'changes_requested' }),
      itemRowFixture({
        id: 1051,
        key: 'CP-1051',
        title: 'Card balance transfer email',
        product: 'credit_card',
        channel: 'email',
        status: 'in_review',
      }),
      itemRowFixture({
        id: 1060,
        key: 'CP-1060',
        title: 'Prequal landing page refresh',
        product: 'mortgage_prequal',
        channel: 'landing_page',
        status: 'submitted',
        assignee: null,
      }),
      itemRowFixture({
        id: 1012,
        key: 'CP-1012',
        title: 'Spring PL search ads',
        channel: 'paid_search',
        status: 'approved',
      }),
      itemRowFixture({
        id: 1003,
        key: 'CP-1003',
        title: 'Affiliate comparison page',
        channel: 'affiliate_page',
        status: 'needs_rereview',
        reopen_reason: 'terms_changed',
      }),
    ],
    item: {
      status: 'changes_requested',
      latest_decision: {
        ...DECISION_APPROVED,
        outcome: 'changes_requested',
        version_n: 2,
        reason: 'Add the full APR range next to “as low as”.',
      },
    },
  });
  await page.goto('/mine');
  await capture(page, 'mine');
});
