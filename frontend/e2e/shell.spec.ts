import { expect, test } from '@playwright/test';

test('app shell renders with navigation and a quiet API status', async ({ page }) => {
  await page.route('**/api/health', (route) => route.fulfill({ json: { status: 'ok', database: true } }));

  await page.goto('/');

  await expect(page.getByRole('link', { name: 'ClearPath Compliance Review' })).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Primary' });
  await expect(nav.getByRole('link', { name: 'Queue' })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible();
  await expect(page.getByText('Server connected')).toBeAttached();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('API status is prominent when the API is down', async ({ page }) => {
  await page.route('**/api/health', (route) => route.fulfill({ status: 503, json: { detail: 'down' } }));

  await page.goto('/');

  await expect(page.getByRole('alert')).toContainText("Can't reach server");
});

test('design gallery is reachable by URL and absent from the nav', async ({ page }) => {
  await page.route('**/api/health', (route) => route.fulfill({ json: { status: 'ok', database: true } }));

  await page.goto('/dev/design');

  await expect(page.getByRole('heading', { name: 'Design system' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' })).not.toContainText('Design');
});
