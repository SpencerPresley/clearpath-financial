import { expect, test } from '@playwright/test';

import { ME, stubApi } from './api.ts';

test('app shell renders with navigation and a quiet API status', async ({ page }) => {
  await stubApi(page, { me: ME.all });

  await page.goto('/');

  await expect(page.getByRole('link', { name: 'ClearPath Compliance Review' })).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Primary' });
  await expect(nav.getByRole('link', { name: 'Queue' })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('heading', { name: 'Queue', level: 1 })).toBeVisible();
  await expect(page.getByText('Server connected')).toBeAttached();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('API status is prominent when the API is down', async ({ page }) => {
  await stubApi(page);
  await page.route('**/api/health', (route) => route.fulfill({ status: 503, json: { detail: 'down' } }));

  await page.goto('/');

  await expect(page.getByRole('alert').filter({ hasText: "Can't reach server" })).toBeVisible();
});

test('design gallery is reachable by URL and absent from the nav', async ({ page }) => {
  await stubApi(page);

  await page.goto('/dev/design');

  await expect(page.getByRole('heading', { name: 'Design system' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' })).not.toContainText('Design');
});

test('nav follows the signed-in roles from /api/me', async ({ page }) => {
  await stubApi(page, { me: ME.reviewer });

  await page.goto('/');

  const nav = page.getByRole('navigation', { name: 'Primary' });
  await expect(nav.getByRole('link', { name: 'Queue' })).toBeVisible();
  await expect(nav).not.toContainText('Metrics');
  await expect(nav).not.toContainText('Import');
});

test('signed out shows the sign-in form', async ({ page }) => {
  await stubApi(page, { me: 'signed-out' });

  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' })).toHaveCount(0);
});
