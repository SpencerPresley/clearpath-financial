import { expect, test } from '@playwright/test';

import { ME_LIBRARY_REVIEWER } from '../src/test/fixtures/library';
import { stubLibraryApi } from './libraryImportApi';

test('library: filter the approved view, export it, then find a precedent and its evidence pack', async ({
  page,
}) => {
  const api = await stubLibraryApi(page, { me: ME_LIBRARY_REVIEWER });
  await page.goto('/');
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Library' }).click();

  const table = page.getByRole('table', { name: 'Approved to run' });
  await expect(table.getByRole('link', { name: /Holiday personal loan email/ })).toBeVisible();
  const legacy = table.getByRole('row', { name: /CP-412/ });
  await legacy.getByRole('button', { name: "Why there's no evidence pack for CP-412" }).hover();
  await expect(page.getByRole('tooltip')).toContainText('no decision record to pack');
  await page.mouse.move(0, 0);
  await expect(page.getByRole('tooltip')).toBeHidden();

  await page.getByRole('button', { name: 'Channel' }).click();
  await page.getByRole('menuitemcheckbox', { name: 'Email' }).click();
  await page.keyboard.press('Escape');
  await expect(page).toHaveURL(/channel=%5B%22email%22%5D/);

  await page.getByRole('button', { name: 'Export' }).click();
  await page.getByRole('menuitem', { name: /Export view \(\.xlsx\)/ }).click();
  await expect(page.getByText('Building export…')).toBeVisible();
  const download = page.getByRole('link', { name: 'Download' });
  await expect(download).toBeVisible();
  // A real <a download> (the mutator would read the xlsx as text); the browser saves it under this name.
  await expect(download).toHaveAttribute('href', '/api/exports/9/download');
  await expect(download).toHaveAttribute('download', 'clearpath-export-2026-10-24.xlsx');
  expect(api.posted.find((p) => p.path === '/exports')?.body).toEqual({
    filters: { channel: ['email'], status: ['approved'] },
    sort: 'updated',
    include_evidence_packs: false,
  });

  await page.getByRole('tab', { name: 'Precedents' }).click();
  await page.getByRole('searchbox', { name: 'Search approved copy' }).fill("won't affect your credit score");
  const hits = page.getByRole('list', { name: 'Precedents' });
  await expect(hits.locator('mark').first()).toHaveText("won't affect your credit score");
  await expect(page).toHaveURL(/tab=precedents/);
  const lapsed = hits.getByRole('listitem').nth(1);
  await expect(lapsed.getByText('Re-review')).toBeVisible();
  await expect(lapsed.getByText('Matched v2')).toBeVisible();

  const first = hits.getByRole('listitem').first();
  await first.getByRole('button', { name: 'Evidence pack for CP-1088' }).click();
  await expect(first.getByRole('link', { name: 'Download evidence pack for CP-1088' })).toHaveAttribute(
    'href',
    '/api/exports/38/download',
  );
});
