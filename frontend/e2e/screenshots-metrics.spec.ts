/*
 * UI-review screenshots of the metrics page's stubbed states (spec §8.4). Skipped unless SCREENSHOTS=1:
 *   SCREENSHOTS=1 npx playwright test e2e/screenshots-metrics.spec.ts
 * Output: docs/plan/reviews/ui/screens/metrics-<state>-<width>.png. The data states are also captured against
 * a real backend (see docs/plan/reports/screens.md).
 */
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

import { stubMetrics } from './metricsApi.ts';
import type { MetricsStub } from './metricsApi.ts';

const OUT = '../docs/plan/reviews/ui/screens';
const SIZES = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
] as const;

test.skip(process.env.SCREENSHOTS !== '1', 'set SCREENSHOTS=1 to capture UI-review screenshots');

const shots: { name: string; mode: MetricsStub; path?: string; ready: (page: Page) => Promise<void> }[] = [
  {
    name: 'stub-chart',
    mode: 'data',
    ready: (page) => expect(page.getByRole('img', { name: /Throughput by week/ })).toBeVisible(),
  },
  {
    name: 'stub-drill-open',
    mode: 'data',
    path: '/metrics?drill=time_to_fix_live&open=true',
    ready: (page) => expect(page.getByRole('region', { name: /open now/ })).toBeVisible(),
  },
  {
    name: 'loading',
    mode: 'loading',
    ready: (page) => expect(page.getByRole('status', { name: 'Loading the numbers' })).toBeVisible(),
  },
  {
    name: 'empty',
    mode: 'empty',
    path: '/metrics?range=4w',
    ready: (page) => expect(page.getByRole('heading', { name: 'No decisions in this period' })).toBeVisible(),
  },
  {
    name: 'error',
    mode: 'error',
    ready: (page) =>
      // The query client retries 5xx before showing the error.
      expect(page.getByText("Couldn't load the trend.", { exact: false })).toBeVisible({ timeout: 20_000 }),
  },
  {
    name: 'partial',
    mode: 'partial',
    path: '/metrics?view=table',
    ready: async (page) => {
      await expect(page.getByRole('table', { name: /Throughput by week/ })).toBeVisible();
      await expect(page.getByText('Metrics are temporarily unavailable.')).toBeVisible({ timeout: 20_000 });
    },
  },
];

for (const size of SIZES) {
  for (const shot of shots) {
    test(`metrics ${shot.name} ${String(size.width)}`, async ({ page }) => {
      await page.setViewportSize(size);
      await stubMetrics(page, shot.mode);
      await page.goto(shot.path ?? '/metrics');
      await shot.ready(page);
      await page.screenshot({ path: `${OUT}/metrics-${shot.name}-${String(size.width)}.png` });
    });
  }
}
