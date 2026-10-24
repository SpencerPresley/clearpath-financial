import { expect, test } from '@playwright/test';

import { importJob, reimportPreview } from '../src/test/fixtures/imports';
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

  // Values always shows, with what the importer read each value as.
  const values = page.getByRole('table', { name: 'Value mapping' });
  await expect(
    values.getByRole('row', { name: /“CardPerks”.*CardPerks Weekly.*Matched spelling/ }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Save and continue' }).click();

  await expect(page.getByRole('heading', { name: 'Preview' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Warnings · 4/ })).toBeVisible();
  await expect(
    page.getByRole('table', { name: 'Warnings' }).getByRole('row', { name: /^92 .*Imports under a new ID/ }),
  ).toBeVisible();

  await page.getByRole('button', { name: 'Import 178 items' }).click();
  await expect(page.getByText('Importing 178 items…')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Imported 178 items' })).toBeVisible();
  expect(api.posted.map((p) => `${p.method} ${p.path}`)).toEqual([
    'POST /imports/sample',
    'PUT /imports/7/mapping',
    'PUT /imports/7/mapping',
    'POST /imports/7/commit',
  ]);

  await page
    .getByRole('table', { name: 'Imported items' })
    .getByRole('link', { name: 'PL Credit Card Payoff postcard' })
    .click();
  await expect(page).toHaveURL(/\/items\/400$/);
});

test('import: after a seed, the sample says its rows are already imported and opens that import', async ({
  page,
}) => {
  await stubLibraryApi(page, { job: importJob({ status: 'mapped' }), preview: reimportPreview() });
  await page.goto('/import?job=7&step=preview');

  await expect(page.getByText(/178 rows already imported from this tracker/)).toBeVisible();
  await expect(page.getByRole('button', { name: /^Warnings/ })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'See how each row was imported' })).toHaveAttribute(
    'href',
    '/import?job=1&step=preview',
  );
  await expect(page.getByRole('button', { name: 'Import 0 items' })).toHaveCount(0);
  await expect(page.getByText('Nothing new to import.')).toBeVisible();
});
