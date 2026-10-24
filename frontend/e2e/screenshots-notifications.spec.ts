/*
 * UI-review screenshots of the notifications inbox (spec §8.4). Skipped unless SCREENSHOTS=1:
 *   SCREENSHOTS=1 npx playwright test e2e/screenshots-notifications.spec.ts
 * Output: docs/plan/reviews/ui/notifications/<state>-1440.png, the inbox open over the queue.
 */
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

import type { NotificationOut } from '../src/api/generated/model';
import { INBOX_ROWS, MANY_ROWS } from '../src/test/fixtures/notifications';
import { NOW } from '../src/test/fixtures/review';
import { stubNotifications } from './notificationsApi.ts';
import type { InboxMode } from './notificationsApi.ts';
import { stubApi } from './stubApi.ts';

const OUT = '../docs/plan/reviews/ui/notifications';

test.skip(process.env.SCREENSHOTS !== '1', 'set SCREENSHOTS=1 to capture UI-review screenshots');
test.use({ viewport: { width: 1440, height: 900 }, timezoneId: 'UTC' });

const shots: {
  name: string;
  rows: NotificationOut[];
  mode?: InboxMode;
  ready: (page: Page) => Promise<void>;
}[] = [
  {
    name: 'unread',
    rows: INBOX_ROWS,
    ready: (page) => expect(page.getByRole('option', { name: /Dana Reyes requested changes/ })).toBeVisible(),
  },
  {
    name: 'empty',
    rows: [],
    ready: (page) => expect(page.getByRole('heading', { name: 'No notifications' })).toBeVisible(),
  },
  {
    name: 'many',
    rows: MANY_ROWS,
    ready: (page) => expect(page.getByRole('group', { name: 'Earlier' })).toBeVisible(),
  },
  {
    name: 'loading',
    rows: [],
    mode: 'loading',
    ready: (page) => expect(page.getByRole('status', { name: 'Loading notifications' })).toBeVisible(),
  },
  {
    name: 'error',
    rows: [],
    mode: 'error',
    // The query client retries 5xx before showing the error.
    ready: (page) =>
      expect(page.getByText('Notifications are temporarily unavailable.')).toBeVisible({ timeout: 20_000 }),
  },
];

for (const shot of shots) {
  test(`notifications ${shot.name}`, async ({ page }) => {
    await page.clock.setFixedTime(new Date(NOW));
    await stubApi(page);
    await stubNotifications(page, shot.rows, shot.mode);
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Queue', level: 1 })).toBeVisible();

    await page.getByRole('button', { name: /^Notifications/ }).click();
    await shot.ready(page);
    await expect(page.locator('.app-inbox')).toHaveCSS('opacity', '1'); // past the fade-in
    await page.mouse.move(0, 0); // no hover on the first row
    await page.screenshot({ path: `${OUT}/${shot.name}-1440.png` });
  });
}

test('notifications bell with unread', async ({ page }) => {
  await page.clock.setFixedTime(new Date(NOW));
  await stubApi(page);
  await stubNotifications(page, MANY_ROWS);
  await page.goto('/');
  await expect(page.getByRole('button', { name: /Notifications, \d+ unread/ })).toBeVisible();
  await page.screenshot({ path: `${OUT}/bell-1440.png`, clip: { x: 1040, y: 0, width: 400, height: 48 } });
});
