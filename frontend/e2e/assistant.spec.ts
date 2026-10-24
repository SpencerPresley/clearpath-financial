import { expect, test } from '@playwright/test';

import { INTERRUPT_ID, stubAssistant } from './stubAssistant';
import { stubApi } from './stubApi';

test('the assistant drafts an email, a person approves it, and it lands in the Outbox', async ({ page }) => {
  await stubApi(page);
  const assistant = await stubAssistant(page);
  const origins = new Set<string>();
  page.on('request', (request) => origins.add(new URL(request.url()).origin));
  await page.goto('/');

  await page.getByRole('button', { name: 'Assistant' }).click();
  const panel = page.getByRole('complementary', { name: 'Assistant' });
  const box = panel.getByRole('textbox', { name: 'Message the assistant' });
  await expect(box).toBeFocused();
  await box.fill('Email compliance about CP-1');
  await box.press('Enter');

  const card = panel.getByRole('region', { name: 'Email draft — needs your approval' });
  await expect(card).toBeVisible();
  await expect(card.getByRole('list', { name: 'Recipients' })).toHaveText('compliance@clearpath.demo');
  await expect(card.getByText('CP-1 findings summary')).toBeVisible();
  await expect(box).toBeDisabled();
  expect(assistant.outbox).toHaveLength(0);

  await card.getByRole('button', { name: 'Send email' }).click();
  await expect(panel.getByText('Sent. It is in the Outbox.')).toBeVisible();
  await expect(card).toBeHidden();
  // The SDK also POSTs .../history on hydrate (AssistantTransport.apiUrl keeps it on our origin); not a write.
  expect(assistant.posted.map((p) => p.path).filter((path) => !path.endsWith('/history'))).toEqual([
    '/threads',
    '/threads/0b4c7a4e-0000-4000-8000-000000000001/runs',
    `/threads/0b4c7a4e-0000-4000-8000-000000000001/interrupts/${INTERRUPT_ID}`,
  ]);
  expect(assistant.posted.find((p) => p.path.includes('/interrupts/'))?.body).toEqual({ type: 'approve' });

  // The app's own record of the send (not the model's words) links straight to the Outbox row.
  await expect(panel.getByText('Sent to compliance@clearpath.demo · approved by you')).toBeVisible();
  await panel.getByRole('link', { name: 'Open in Outbox' }).click();
  await expect(page).toHaveURL(/\/outbox\?email=1$/);
  const row = page
    .getByRole('table', { name: 'Sent emails' })
    .getByRole('row', { name: /CP-1 findings summary/ });
  await expect(row).toBeVisible();
  await expect(row.getByRole('link', { name: 'CP-1' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'CP-1 findings summary' })).toBeVisible();

  // The panel stays open beside the Outbox; the conversation is still there.
  await expect(panel.getByText('Sent. It is in the Outbox.')).toBeVisible();
  // Nothing went anywhere but the app's own origin (no SDK default of localhost:8123).
  expect([...origins]).toEqual([new URL(page.url()).origin]);
});
