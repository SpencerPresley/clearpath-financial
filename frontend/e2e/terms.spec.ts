import { expect, test } from '@playwright/test';

import { stubTermsPartners } from './termsPartnersApi.ts';

test('a lead previews a personal loan rate change and publishes v13', async ({ page }) => {
  const posted = await stubTermsPartners(page);
  await page.goto('/');
  await page.getByRole('link', { name: 'Offer terms' }).click();
  await expect(page).toHaveURL(/\/terms$/);
  await expect(page.getByRole('region', { name: 'Personal loan terms in effect' })).toContainText('7.49%');

  await page.getByRole('button', { name: 'Edit terms' }).click();
  const form = page.getByRole('form', { name: 'Edit personal loan terms' });
  const publish = form.getByRole('button', { name: /Publish v13/ });
  await expect(publish).toBeDisabled();

  await form.getByRole('textbox', { name: 'APR min' }).fill('12.99');
  const impact = page.getByRole('region', { name: 'Impact of publishing v13' });
  await expect(impact).toContainText('14 approved items quote v12; 9 will need re-review, 5 will expire.');
  await expect(page.getByRole('table', { name: 'Affected items' }).getByRole('row')).toHaveCount(15);
  await expect(publish).toBeEnabled();

  await publish.click();
  const dialog = page.getByRole('alertdialog', { name: 'Publish personal loan terms v13?' });
  await expect(dialog).toContainText('7.49% → 12.99%');
  await dialog.getByRole('button', { name: 'Publish v13' }).click();

  await expect(page.getByText('Published personal loan terms v13')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Personal loan terms in effect' })).toContainText('v13');
  const publishCall = posted.find((p) => p.method === 'POST' && p.path === '/api/terms');
  expect(publishCall?.body).toMatchObject({
    product: 'personal_loan',
    based_on_terms_id: 112,
    values: { apr_min: '12.99' },
  });
});
