import { expect, test } from '@playwright/test';

import type { SubmitItemIn } from '../src/api/generated/model';
import { stubApi } from './stubApi';

test('a marketer sees live findings while typing and the open count before submitting', async ({ page }) => {
  const api = await stubApi(page);
  await page.goto('/submit');

  await page.getByLabel('Title').fill('Fall personal loan promo');
  await page.getByRole('button', { name: /Product/ }).click();
  await page.getByRole('option', { name: 'Personal loan' }).click();
  await page.getByRole('button', { name: /Channel/ }).click();
  await page.getByRole('option', { name: 'Paid social' }).click();
  await page.getByLabel('First run').fill('2026-11-01');

  const copy = page.getByRole('textbox', { name: /copy/i }).first();
  await copy.fill('Need cash fast? 💸 Personal loans as low as 5.99% APR.');
  // Highlighted in the copy, after an emoji, within the live-check budget.
  await expect(page.locator('.app-copy-backdrop mark')).toHaveText('as low as', { timeout: 2000 });
  await expect(page.getByText('Rate claim needs the full APR range')).toBeVisible();

  await page.getByRole('button', { name: 'Submit', exact: true }).click();
  await expect(page.getByText(/1 open finding/)).toBeVisible();
  expect(api.posted.filter((p) => p.path === '/items')).toHaveLength(0);

  await page.getByRole('button', { name: 'Submit anyway' }).click();
  await expect(page).toHaveURL(/\/items\/1077$/);
  const submitted = api.posted.find((p) => p.path === '/items')?.body as SubmitItemIn;
  expect(submitted).toMatchObject({
    title: 'Fall personal loan promo',
    product: 'personal_loan',
    channel: 'paid_social',
  });
});
