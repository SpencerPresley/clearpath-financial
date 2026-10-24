import { expect, test } from '@playwright/test';

import { stubSearch } from './searchApi.ts';
import { stubApi } from './stubApi.ts';

test('jump to an item from anywhere: / focuses, a CP key and Enter opens it', async ({ page }) => {
  await stubApi(page);
  const search = await stubSearch(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Queue', level: 1 })).toBeVisible();
  const box = page.getByRole('combobox', { name: 'Jump to item' });

  await page.locator('body').press('/');
  await expect(box).toBeFocused();
  await expect(box).toHaveValue(''); // the slash focuses, it isn't typed

  await box.pressSequentially('CP-1042');
  await expect(page.getByRole('option', { name: /CP-1042/ })).toBeVisible();
  await page.keyboard.press('Enter');

  await expect(page).toHaveURL(/\/items\/1042$/);
  await expect(page.getByRole('heading', { name: /Fall personal loan promo — paid social/ })).toBeVisible();
  await expect(box).toHaveValue('');
  await expect(page.locator('#main')).toBeFocused();
  expect(search.asked).toEqual(['CP-1042']); // debounced: one request for the settled text
});

test('⌘K / Ctrl+K finds a legacy item by its old tracker ID', async ({ page }) => {
  await stubApi(page);
  await stubSearch(page);
  await page.goto('/');
  const box = page.getByRole('combobox', { name: 'Jump to item' });
  await expect(box).toBeVisible();

  await page.keyboard.press('ControlOrMeta+k');
  await expect(box).toBeFocused();
  await box.pressSequentially('MCR-26');

  const option = page.getByRole('option', { name: /CP-1188/ });
  await expect(option).toContainText('MCR-26-045');
  await expect(option).toContainText('Approved');
});
