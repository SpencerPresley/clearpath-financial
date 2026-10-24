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

test('Enter right after typing opens what was typed, never the previous search’s top row', async ({
  page,
}) => {
  await stubApi(page);
  await stubSearch(page);
  await page.goto('/');
  const box = page.getByRole('combobox', { name: 'Jump to item' });
  await expect(box).toBeVisible();

  // A pasted key and an immediate Enter: no results on screen yet.
  await box.focus();
  await box.fill('CP-1061');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/items\/1061$/);

  // "fall" lists CP-1042 first; refining to "fall promo landing" and pressing Enter at once must open CP-1070.
  await page.keyboard.press('ControlOrMeta+k');
  await box.pressSequentially('fall');
  await expect(page.getByRole('option', { name: /CP-1042/ })).toBeVisible();
  await box.pressSequentially(' promo landing');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/items\/1070$/);
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
