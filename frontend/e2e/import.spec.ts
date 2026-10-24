import { expect, test } from '@playwright/test';

import { stubLibraryApi } from './libraryImportApi';

test('import: load the sample, keep the column guesses, preview, commit, and open an imported item', async ({
  page,
}) => {
  const api = await stubLibraryApi(page);
  await page.goto('/');
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Import' }).click();
  await expect(page.getByRole('table', { name: 'Recent imports' })).toBeVisible();

  await page.getByRole('button', { name: 'Load sample tracker' }).click();
  const columns = page.getByRole('table', { name: 'Column mapping' });
  await expect(columns.getByRole('row', { name: /Request ID/ })).toBeVisible();
  await page.getByRole('button', { name: 'Save and continue' }).click();

  await expect(page.getByRole('heading', { name: 'Preview' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Warnings · 4/ })).toBeVisible();
  await expect(page.getByRole('table', { name: 'Warnings' }).getByRole('row', { name: /^92/ })).toBeVisible();

  await page.getByRole('button', { name: 'Import 178 items' }).click();
  await expect(page.getByText('Importing 178 items…')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Imported 178 items' })).toBeVisible();
  expect(api.posted.map((p) => `${p.method} ${p.path}`)).toEqual([
    'POST /imports/sample',
    'PUT /imports/7/mapping',
    'POST /imports/7/commit',
  ]);

  await page
    .getByRole('table', { name: 'Imported items' })
    .getByRole('link', { name: 'PL Credit Card Payoff postcard' })
    .click();
  await expect(page).toHaveURL(/\/items\/400$/);
});
