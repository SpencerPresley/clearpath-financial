import { expect, test } from '@playwright/test';

import type { DecisionIn } from '../src/api/generated/model';
import { stubApi } from './stubApi';

test('a reviewer triages every finding by keyboard and requests the accepted changes', async ({ page }) => {
  const api = await stubApi(page);
  await page.goto('/items/1042');

  const approve = page.getByRole('button', { name: 'Approve', exact: true });
  await expect(page.getByRole('heading', { name: 'Fall personal loan promo — paid social' })).toBeVisible();
  await expect(approve).toBeDisabled();
  await expect(page.getByText('4 findings to triage')).toBeVisible();

  // The highlight sits on the quoted text even though an emoji precedes it (code-point offsets).
  await expect(page.locator('mark[data-mark-ids~="9003"]')).toHaveText('no impact on your credit score');

  await page.keyboard.press('n');
  await expect(page.locator('#finding-9001')).toHaveAttribute('aria-current', 'true');
  await page.keyboard.press('a');
  await expect(page.locator('#finding-9001')).toContainText('Accepted by Dana Reyes');
  // Triage advances to the next open finding; cards keep their place.
  await expect(page.locator('#finding-9003')).toHaveAttribute('aria-current', 'true');

  await page.keyboard.press('d');
  const reason = page.getByLabel('Reason for dismissing');
  await expect(reason).toBeFocused();
  await reason.fill('Disclosed on the landing page; this ad links there.');
  await reason.press('Enter');
  await expect(page.locator('#finding-9003')).toContainText('Disclosed on the landing page');

  await expect(page.locator('#finding-9002')).toHaveAttribute('aria-current', 'true');
  await page.keyboard.press('a');
  await expect(page.locator('#finding-9004')).toHaveAttribute('aria-current', 'true');
  await page.keyboard.press('a');
  await expect(page.getByText('findings to triage')).toHaveCount(0);
  // Accepted findings are required changes, so a plain Approve stays off.
  await expect(page.getByText('3 accepted findings need a change')).toBeVisible();
  await expect(approve).toBeDisabled();

  await page.getByRole('button', { name: 'Request changes' }).click();
  const changes = page.getByLabel('Changes needed');
  await expect(changes).toHaveValue(/Rate claim needs the full APR range/);
  await page.getByRole('button', { name: 'Request changes' }).last().click();

  await expect(page.getByText(/Changes requested v2 by Dana Reyes/)).toBeVisible();
  const decision = api.posted.find((p) => p.path === '/items/1042/decisions');
  expect(decision?.body).toMatchObject({
    outcome: 'changes_requested',
    version_n: 2,
    evidence_attachment_ids: [],
  } satisfies Partial<DecisionIn>);
});

test('shortcuts help opens with ? and typing in a field does not trigger shortcuts', async ({ page }) => {
  await stubApi(page);
  await page.goto('/items/1042?tab=comments');
  await page.getByLabel('Comment on v2').fill('need a decision by friday');
  await expect(page.locator('[aria-current="true"]')).toHaveCount(0);

  await page.locator('body').click({ position: { x: 5, y: 300 } });
  await page.keyboard.press('Shift+?');
  await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible();
});
