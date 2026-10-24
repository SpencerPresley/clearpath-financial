/*
 * UI-review captures for the fast-track / AI-status polish (spec §8.4), not assertions. Runs only with POLISH=1:
 *   POLISH=1 npx playwright test e2e/polish.spec.ts
 * Writes to docs/plan/reviews/ui/polish/ at 1440x900.
 */
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

import { DECISION_APPROVED, FINDINGS_OPEN, triaged, versionFixture } from '../src/test/fixtures/review';
import { stubApi } from './stubApi';
import type { StubOptions } from './stubApi';

const OUT = '../docs/plan/reviews/ui/polish';

test.skip(!process.env.POLISH, 'screenshots only with POLISH=1');

async function capture(page: Page, name: string) {
  await page.evaluate(() => document.fonts.ready);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(150);
  await page.screenshot({ path: `${OUT}/${name}-1440x900.png` });
}

const summaries = (origin: 'fast_track') => [
  {
    id: 501,
    n: 1,
    origin: 'submission' as const,
    author: versionFixture(1).author,
    created_at: versionFixture(1).created_at,
    based_on_n: null,
  },
  {
    id: 502,
    n: 2,
    origin,
    author: { id: 0, name: 'System' },
    created_at: '2026-10-24T08:00:00Z',
    based_on_n: 1,
  },
];

function rereview(numbersChange: boolean): StubOptions {
  const v1 = versionFixture(1).content_text;
  return {
    item: {
      status: 'needs_rereview',
      reopen_reason: 'terms_changed',
      llm_check_status: 'skipped',
      live_placements_count: 1,
      latest_decision: { ...DECISION_APPROVED, version_n: 1 },
      current_version: versionFixture(2, {
        origin: 'fast_track',
        author: { id: 0, name: 'System' },
        based_on_n: 1,
        content_text: numbersChange ? v1.replace('5.99%', '6.49%') : v1,
      }),
      versions: summaries('fast_track'),
      numbers_change: numbersChange,
    },
    findings: [],
  };
}

const withoutAi = triaged(FINDINGS_OPEN).filter((f) => f.source !== 'llm');

test('rereview-numbers-unchanged', async ({ page }) => {
  await stubApi(page, rereview(false));
  await page.goto('/items/1042');
  await expect(page.getByText('Numbers unchanged.')).toBeVisible();
  await page.getByRole('button', { name: 'Fast-track approve v2' }).click();
  await capture(page, 'rereview-numbers-unchanged');
});

test('rereview-newer-version-arrived', async ({ page }) => {
  const options = rereview(true);
  const state = await stubApi(page, options);
  await page.route('**/api/items/1042/fast-track-approve', async (route) => {
    // A second terms change generated v3 while the reviewer had v2 open.
    const v3 = versionFixture(2, {
      id: 503,
      n: 3,
      origin: 'fast_track',
      author: { id: 0, name: 'System' },
      based_on_n: 1,
      content_text: versionFixture(1).content_text.replace('5.99%', '6.99%'),
    });
    state.item = {
      ...state.item,
      current_version_n: 3,
      current_version: v3,
      versions: [...state.item.versions, { ...summaries('fast_track')[1], id: 503, n: 3 }],
    };
    state.findings[3] = [];
    await route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 'stale_version',
        message: "v2 isn't the current version (v3). Reload the item.",
        details: { version_n: 2, current_n: 3 },
      }),
    });
  });
  await page.goto('/items/1042');
  await page.getByRole('button', { name: 'Fast-track approve v2' }).click();
  await page.getByLabel('Reason').fill('Only the APR floor changed.');
  await page.getByRole('button', { name: 'Fast-track approve', exact: true }).last().click();
  await expect(page.getByText(/A newer version, v3, arrived/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Fast-track approve v3' })).toBeVisible();
  await capture(page, 'rereview-newer-version-arrived');
});

test('ai-running-then-done', async ({ page }) => {
  const state = await stubApi(page, { item: { llm_check_status: 'running' }, findings: withoutAi });
  await page.goto('/items/1042');
  await expect(page.getByText('AI check running…')).toBeVisible();
  await capture(page, 'ai-running');
  // The worker finishes: the next poll (3 s) brings the status, the findings, and the gate.
  state.item = { ...state.item, llm_check_status: 'succeeded' };
  state.findings[2] = triaged(FINDINGS_OPEN).map((f) =>
    f.source === 'llm' ? { ...f, state: 'open' as const, resolved_by: null, resolved_at: null } : f,
  );
  await expect(page.getByText(/AI check finished/)).toBeVisible({ timeout: 8000 });
  await capture(page, 'ai-done');
});

test('ai-failed-reason', async ({ page }) => {
  await stubApi(page, {
    item: {
      llm_check_status: 'failed',
      llm_check_failure_code: 'provider_unavailable',
      llm_check_failure_reason:
        "The AI service didn't answer after 4 tries. Couldn't reach the model provider.",
    },
    findings: withoutAi,
  });
  await page.goto('/items/1042');
  await expect(page.getByText(/AI check failed:/)).toBeVisible();
  await capture(page, 'ai-failed-reason');
});

test('ai-not-configured', async ({ page }) => {
  await stubApi(page, {
    item: {
      llm_check_status: 'failed',
      llm_check_failure_code: 'not_configured',
      llm_check_failure_reason: "The AI check didn't run: no Anthropic API key is configured here.",
    },
    findings: withoutAi,
  });
  await page.goto('/items/1042');
  await expect(page.getByText(/AI review isn’t configured on this server/)).toBeVisible();
  await capture(page, 'ai-not-configured');
});
