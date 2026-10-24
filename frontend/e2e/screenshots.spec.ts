/*
 * UI-review screenshots of every queue state (spec §8.4). Skipped unless SCREENSHOTS=1:
 *   SCREENSHOTS=1 npx playwright test e2e/screenshots.spec.ts
 * Output: docs/plan/reviews/ui/queue/<state>-<width>.png
 */
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

import { ME, stubApi } from './api.ts';
import type { StubOptions } from './api.ts';

const OUT = '../docs/plan/reviews/ui/queue';
const SIZES = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
] as const;

test.skip(process.env.SCREENSHOTS !== '1', 'set SCREENSHOTS=1 to capture UI-review screenshots');

interface Shot {
  name: string;
  path?: string;
  stub?: StubOptions;
  ready?: (page: Page) => Promise<void>;
}

const ACTIVE =
  '/?view=active&status=%5B%22submitted%22%2C%22in_review%22%2C%22changes_requested%22%2C%22needs_rereview%22%5D&is_legacy=false';

const shots: Shot[] = [
  {
    name: 'table',
    path: ACTIVE,
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
    },
  },
  {
    name: 'loading',
    stub: { items: 'hang', stats: 'hang' },
    ready: async (page) => {
      await expect(page.getByRole('status', { name: 'Loading the queue' })).toBeVisible();
    },
  },
  {
    name: 'empty-my-queue',
    stub: { rows: [], stats: { mine: 0 } },
    ready: async (page) => {
      await expect(page.getByText('4 unassigned items')).toBeVisible();
    },
  },
  {
    name: 'empty-filtered',
    path: '/?view=mine&mine=true&risk_tier=%5B%22high%22%5D&product=%5B%22mortgage_prequal%22%5D',
    stub: { rows: [] },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: 'No items match these filters' })).toBeVisible();
    },
  },
  {
    name: 'error',
    stub: { items: 503 },
    ready: async (page) => {
      // The query retries three times with backoff before showing the error.
      await expect(page.getByRole('heading', { name: "Couldn't load the queue" })).toBeVisible({
        timeout: 15_000,
      });
    },
  },
  {
    name: 'partial',
    path: ACTIVE,
    stub: { stats: 500, views: 500 },
    ready: async (page) => {
      await expect(page.getByText("Couldn't load queue counts.")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText("Couldn't load saved views.")).toBeVisible({ timeout: 15_000 });
    },
  },
  {
    name: 'drawer',
    path: `${ACTIVE}&item=1047`,
    ready: async (page) => {
      await expect(
        page.getByRole('complementary', { name: 'Preview CP-1047' }).getByText('2 blocking'),
      ).toBeVisible();
    },
  },
  {
    name: 'board',
    path: `${ACTIVE}&layout=board`,
    stub: { me: ME.lead },
    ready: async (page) => {
      await expect(
        page.getByRole('grid', { name: 'Approved · last 14 days' }).getByRole('row').first(),
      ).toBeVisible();
    },
  },
  {
    name: 'filter-menu',
    path: ACTIVE,
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      await page.getByRole('button', { name: /^Status/ }).click();
      await page.getByRole('menuitemcheckbox', { name: 'Changes requested' }).click();
      await expect(page.getByRole('menu')).toBeVisible();
    },
  },
  {
    name: 'more-filters',
    path: ACTIVE,
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      await page.getByRole('button', { name: 'More filters' }).click();
      await page.getByRole('menuitem', { name: 'Product' }).hover();
      await expect(page.getByRole('menu', { name: 'Product' })).toBeVisible();
    },
  },
  {
    name: 'bulk-selection',
    path: ACTIVE,
    stub: { me: ME.lead },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      for (const key of ['CP-1031', 'CP-1044', 'CP-1050']) {
        await page.getByRole('checkbox', { name: `Select ${key}` }).click();
      }
      await expect(page.getByText('3 selected')).toBeVisible();
    },
  },
  {
    name: 'inline-risk',
    path: ACTIVE,
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      await page.getByRole('button', { name: /Risk tier for CP-1044/ }).click();
      await expect(page.getByRole('listbox')).toBeVisible();
    },
  },
  {
    name: 'columns',
    path: ACTIVE,
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      await page.getByRole('button', { name: 'Columns' }).click();
      await expect(page.getByRole('menu', { name: 'Columns' })).toBeVisible();
    },
  },
  {
    name: 'shortcuts',
    path: ACTIVE,
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      await page.keyboard.press('Shift+Slash');
      await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible();
    },
  },
  {
    name: 'focus-row',
    path: ACTIVE,
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      await page.keyboard.press('j');
      await page.keyboard.press('j');
      await page.keyboard.press('j');
    },
  },
  {
    name: 'sign-in',
    stub: { me: 'signed-out' },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
    },
  },
];

for (const size of SIZES) {
  for (const shot of shots) {
    test(`${shot.name} @ ${String(size.width)}`, async ({ page }) => {
      await page.setViewportSize(size);
      await stubApi(page, shot.stub);
      await page.goto(shot.path ?? '/');
      await shot.ready?.(page);
      await page.waitForTimeout(400); // let transitions (120ms) and the scrim fade settle
      await page.screenshot({ path: `${OUT}/${shot.name}-${String(size.width)}.png` });
    });
  }
}
