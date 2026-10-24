import { expect, test } from '@playwright/test';

import { ME, stubApi } from './api.ts';

test('queue table loads in queue order and a filter chip writes the URL', async ({ page }) => {
  await stubApi(page);
  await page.goto('/');

  const table = page.getByRole('table', { name: 'Queue' });
  await expect(table.getByRole('row')).toHaveCount(11); // header + 10
  await expect(table.getByRole('row').nth(1)).toContainText('CP-1031');

  await page.getByRole('button', { name: 'Risk', exact: true }).click();
  await page.getByRole('menuitemcheckbox', { name: 'High' }).click();
  await page.keyboard.press('Escape');
  await expect(page).toHaveURL(/risk_tier=/);
  await expect(page.getByText('Modified')).toBeVisible();
});

test('Enter opens the preview drawer; Escape closes it', async ({ page }) => {
  await stubApi(page);
  await page.goto('/');
  await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();

  await page.keyboard.press('j');
  await page.keyboard.press('Enter');
  const drawer = page.getByRole('complementary', { name: 'Preview CP-1031' });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText('2 blocking')).toBeVisible();
  await expect(page).toHaveURL(/item=1031/);

  await page.keyboard.press('Escape');
  await expect(drawer).toHaveCount(0);
});

test('board toggle shows the five columns and claims by drag', async ({ page }) => {
  await stubApi(page, { me: ME.lead });
  let claimed = '';
  await page.route('**/api/items/*/claim', async (route) => {
    claimed = route.request().url();
    await route.fulfill({ json: { id: 1044 } });
  });
  await page.goto(
    '/?view=active&status=%5B%22submitted%22%2C%22in_review%22%2C%22changes_requested%22%2C%22needs_rereview%22%5D',
  );

  await page.getByRole('radio', { name: 'Board' }).click();
  for (const name of [
    'Submitted',
    'In review',
    'Changes requested',
    'Needs re-review',
    'Approved · last 14 days',
  ]) {
    await expect(page.getByRole('grid', { name })).toBeVisible();
  }
  const card = page.getByRole('grid', { name: 'Submitted' }).getByRole('row', { name: /CP-1044/ });
  await card.dragTo(page.getByRole('grid', { name: 'In review' }));
  await expect.poll(() => claimed).toContain('/api/items/1044/claim');
  await expect(page.getByText('Claimed CP-1044')).toBeVisible();
});

test('the shortcuts help opens with ?', async ({ page }) => {
  await stubApi(page);
  await page.goto('/');
  await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
  await page.keyboard.press('Shift+Slash');
  await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible();
});
