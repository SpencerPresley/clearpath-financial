import { expect, test } from '@playwright/test';

import { stubUsersApi } from './usersApi';

test('admin: Users and Metrics are in the nav; mark a reviewer back in office and give a reviewer the lead role', async ({
  page,
}) => {
  const api = await stubUsersApi(page);
  await page.goto('/library');
  const nav = page.getByRole('navigation', { name: 'Primary' });
  await expect(nav.getByRole('link', { name: 'Metrics' })).toHaveAttribute('href', '/metrics');
  await nav.getByRole('link', { name: 'Users' }).click();

  const table = page.getByRole('table', { name: 'Users' });
  const leah = table.getByRole('row', { name: /Leah Brandt/ });
  await expect(leah.getByText('Out of office')).toBeVisible();
  await expect(leah.getByRole('switch', { name: 'Leah Brandt available' })).not.toBeChecked();
  await leah.locator('.app-switch').click(); // the visible switch; its input is visually hidden
  await expect(leah.getByText('Available', { exact: true })).toBeVisible();

  const dana = table.getByRole('row', { name: /Dana Kim/ });
  await dana.getByRole('button', { name: 'Lead', exact: true }).click();
  await expect(dana.getByRole('button', { name: 'Lead', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  // The only admin can't drop the role; the server's reason shows above the table.
  await table
    .getByRole('row', { name: /Morgan Admin/ })
    .getByRole('button', { name: 'Marketer', exact: true })
    .click();
  await table
    .getByRole('row', { name: /Morgan Admin/ })
    .getByRole('button', { name: 'Admin', exact: true })
    .click();
  await expect(page.getByRole('alert')).toHaveText(
    'Morgan Admin is the only admin. Make someone else an admin first.',
  );

  expect(api.posted.map((p) => `${p.method} ${p.path} ${JSON.stringify(p.body)}`)).toEqual([
    'PATCH /admin/users/3 {"is_available":true}',
    'PATCH /admin/users/2 {"roles":["reviewer","lead"]}',
    'PATCH /admin/users/1 {"roles":["marketer","admin"]}',
    'PATCH /admin/users/1 {"roles":["marketer"]}',
  ]);
});

test('reviewer: the account menu marks you out of office', async ({ page }) => {
  const api = await stubUsersApi(page, {
    me: {
      id: 2,
      display_name: 'Dana Kim',
      email: 'dana@clearpath.demo',
      roles: ['reviewer'],
      effective_roles: ['reviewer'],
      is_available: true,
    },
  });
  await page.goto('/library');

  await page.getByRole('button', { name: 'Dana Kim, account' }).click();
  const panel = page.getByRole('dialog', { name: 'Account' });
  await panel.getByText('Available for new reviews').click();
  await expect(panel.getByText('Out of office')).toBeVisible();
  expect(api.posted).toEqual([{ method: 'PATCH', path: '/me', body: { is_available: false } }]);
});
