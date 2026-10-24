import { expect, test } from '@playwright/test';

test('app shell renders with navigation and API status', async ({ page }) => {
  await page.route('**/api/health', (route) => route.fulfill({ json: { status: 'ok' } }));

  await page.goto('/');

  await expect(page.getByText('ClearPath · Compliance Review')).toBeVisible();
  await expect(
    page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Queue' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible();
  await expect(page.getByText('API: online')).toBeVisible();
});
