import { expect, test } from '@playwright/test';

import { MENTION_ON_1042 } from '../src/test/fixtures/notifications';
import { NOW } from '../src/test/fixtures/review';
import { MENTION_COMMENT, stubNotifications } from './notificationsApi.ts';
import { stubApi } from './stubApi.ts';

test('a mention arrives on the next poll, opens its comment, and is marked read', async ({ page }) => {
  await page.clock.install({ time: new Date(NOW) });
  await stubApi(page);
  const inbox = await stubNotifications(page, []);

  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Notifications', exact: true })).toBeVisible();

  // Receive: the mention lands server-side; the bell picks it up on the next 30 s poll.
  inbox.deliver(MENTION_ON_1042);
  await page.clock.fastForward(30_000);
  const bell = page.getByRole('button', { name: 'Notifications, 1 unread' });
  await expect(bell).toBeVisible();
  await expect(bell).toContainText('1');

  // Open the inbox.
  await bell.click();
  const dialog = page.getByRole('dialog', { name: 'Notifications' });
  await expect(dialog.getByRole('group', { name: 'Today' })).toBeVisible();
  const row = dialog.getByRole('option', {
    name: /Sam Okafor mentioned you on CP-1042 · Fall personal loan promo — paid social/,
  });

  // Navigate (by keyboard: the newest row has focus on open): the item's Comments tab on the comment's version.
  await expect(row).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/items\/1042\?/);
  const url = new URL(page.url());
  expect(url.searchParams.get('tab')).toBe('comments');
  expect(url.searchParams.get('v')).toBe('2');
  await expect(page.getByRole('tab', { name: 'Comments', selected: true })).toBeVisible();
  await expect(page.getByText(MENTION_COMMENT.body)).toBeVisible();
  await expect(dialog).toBeHidden();
  // Focus lands on the page, not back on the bell (whose tooltip would cover the review header), and stays
  // there once the popover's exit has run.
  await page.clock.runFor(1_000);
  await expect(page.locator('#main')).toBeFocused();

  // Read: one receipt, and the bell is quiet again.
  await expect.poll(() => inbox.posted).toEqual(['read 8']);
  await expect(page.getByRole('button', { name: 'Notifications', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Notifications', exact: true }).click();
  await expect(
    dialog.getByRole('option', { name: /Sam Okafor mentioned you/ }).getByText('Unread:'),
  ).toHaveCount(0);
});
