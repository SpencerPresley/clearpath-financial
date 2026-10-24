import { expect, test } from '@playwright/test';

import { stubTermsPartners } from './termsPartnersApi.ts';

test('a lead filters partners, opens one, and pages its findings history', async ({ page }) => {
  await stubTermsPartners(page);
  await page.goto('/');
  await page.getByRole('link', { name: 'Partners' }).click();

  const table = page.getByRole('table', { name: 'Partners' });
  await expect(table.getByRole('row')).toHaveCount(5); // header + 4
  await page.getByRole('searchbox', { name: 'Search partners' }).fill('loan');
  await expect(page).toHaveURL(/q=loan/);
  await expect(table.getByRole('row')).toHaveCount(2);

  await table.getByRole('link', { name: 'LoanFinder' }).click();
  await expect(page.getByRole('heading', { name: 'LoanFinder', level: 1 })).toBeVisible();
  await expect(page.getByRole('table', { name: 'Items from LoanFinder' })).toContainText('Legacy');
  await expect(page.getByRole('region', { name: 'Agreement and evidence' })).toContainText(
    'LoanFinder affiliate agreement 2026.pdf',
  );

  await page.getByRole('tab', { name: /Findings history/ }).click();
  await expect(page).toHaveURL(/tab=findings/);
  const history = page.getByRole('list', { name: 'Findings history, newest first' });
  await expect(history.getByRole('listitem')).toHaveCount(3);
  await page.getByRole('button', { name: 'Load more' }).click();
  await expect(history.getByRole('listitem')).toHaveCount(4);
});
