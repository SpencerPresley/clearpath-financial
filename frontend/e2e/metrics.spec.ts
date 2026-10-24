import { expect, test } from '@playwright/test';

import { stubMetrics } from './metricsApi.ts';

test('a lead opens the items behind a number and reaches the review', async ({ page }) => {
  await stubMetrics(page);
  await page.goto('/');
  await page.getByRole('link', { name: 'Metrics' }).click();

  await expect(page.getByRole('img', { name: /Throughput by week, native and imported/ })).toBeVisible();
  await page.getByRole('button', { name: /Time to first review/ }).click();

  const drill = page.getByRole('region', { name: /Time to first review/ });
  await expect(drill.getByText('Imported · MCR-25-031')).toBeVisible();
  await drill.getByRole('link', { name: 'Spring PL email' }).click();
  await expect(page).toHaveURL(/\/items\/1042$/);
});

test('each waiting count opens its queue view', async ({ page }) => {
  await stubMetrics(page);
  await page.goto('/metrics');
  await page.getByRole('link', { name: 'More than 7 days: 4' }).click();
  await expect(page).toHaveURL(/[?&]waiting=7/);
});
