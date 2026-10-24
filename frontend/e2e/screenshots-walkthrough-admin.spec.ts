/*
 * UI-review screenshots for walkthrough-1 S15 (import demo after a seed) and S16 (Users, availability, workload).
 * Skipped unless SCREENSHOTS=1:
 *   SCREENSHOTS=1 E2E_PORT=4393 npx playwright test e2e/screenshots-walkthrough-admin.spec.ts
 * Output: docs/plan/reviews/ui/walkthrough-fixes/admin/<name>-1440.png
 */
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

import { committedPreview, importJob, importPreview, reimportPreview } from '../src/test/fixtures/imports';
import { ME } from './api';
import { stubApi, USERS } from './api';
import { stubLibraryApi } from './libraryImportApi';
import { stubUsersApi } from './usersApi';

const OUT = '../docs/plan/reviews/ui/walkthrough-fixes/admin';
const SIZE = { width: 1440, height: 900 } as const;
const COMMITTED = importJob({
  id: 7,
  status: 'committed',
  created_at: '2026-08-17T15:30:00Z',
  committed_at: '2026-08-17T15:30:00Z',
  summary: { created: 178, skipped: 2, partners_created: 0 },
});

test.skip(process.env.SCREENSHOTS !== '1', 'set SCREENSHOTS=1 to capture UI-review screenshots');

interface Shot {
  name: string;
  setup: (page: Page) => Promise<unknown>;
  path: string;
  act?: (page: Page) => Promise<void>;
  ready: (page: Page) => Promise<void>;
}

const shots: Shot[] = [
  {
    name: 's15-import-values-inferred',
    setup: (page) => stubLibraryApi(page, { job: importJob({ status: 'mapped' }), preview: importPreview() }),
    path: '/import?job=7&step=values',
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Value mapping' })).toBeVisible();
    },
  },
  {
    name: 's15-import-preview-outcomes',
    setup: (page) => stubLibraryApi(page, { job: importJob({ status: 'mapped' }) }),
    path: '/import?job=7&step=preview',
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Warnings' })).toBeVisible();
    },
  },
  {
    name: 's15-reimport-after-seed',
    setup: (page) =>
      stubLibraryApi(page, { job: importJob({ status: 'mapped' }), preview: reimportPreview() }),
    path: '/import?job=7&step=preview',
    ready: async (page) => {
      await expect(page.getByText(/already imported from this tracker/)).toBeVisible();
    },
  },
  {
    name: 's15-seeded-import-history-preview',
    setup: (page) => stubLibraryApi(page, { job: COMMITTED, preview: committedPreview() }),
    path: '/import?job=7&step=preview',
    ready: async (page) => {
      await expect(page.getByText('Items created')).toBeVisible();
    },
  },
  {
    name: 's15-seeded-import-history-values',
    setup: (page) => stubLibraryApi(page, { job: COMMITTED, preview: committedPreview() }),
    path: '/import?job=7&step=values',
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Value mapping' })).toBeVisible();
    },
  },
  {
    name: 's16-users',
    setup: (page) => stubUsersApi(page),
    path: '/users',
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Users' })).toBeVisible();
    },
  },
  {
    name: 's16-users-add',
    setup: (page) => stubUsersApi(page),
    path: '/users',
    act: async (page) => {
      await page.getByRole('button', { name: 'Add user' }).click();
    },
    ready: async (page) => {
      await expect(page.getByRole('form', { name: 'New user' })).toBeVisible();
    },
  },
  {
    name: 's16-users-last-admin-refused',
    setup: (page) => stubUsersApi(page),
    path: '/users',
    act: async (page) => {
      const me = page.getByRole('table', { name: 'Users' }).getByRole('row', { name: /Morgan Admin/ });
      await me.getByRole('button', { name: 'Lead', exact: true }).click();
      await expect(me.getByRole('button', { name: 'Lead', exact: true })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
      await me.getByRole('button', { name: 'Admin', exact: true }).click();
    },
    ready: async (page) => {
      await expect(page.getByRole('alert')).toBeVisible();
    },
  },
  {
    name: 's16-account-menu-out-of-office',
    setup: (page) =>
      stubUsersApi(page, {
        me: {
          id: 3,
          display_name: 'Leah Brandt',
          email: 'leah@clearpath.demo',
          roles: ['reviewer'],
          effective_roles: ['reviewer'],
          is_available: false,
        },
      }),
    path: '/users',
    act: async (page) => {
      await page.getByRole('button', { name: 'Leah Brandt, account' }).click();
    },
    ready: async (page) => {
      await expect(page.getByRole('dialog', { name: 'Account' }).getByText('Out of office')).toBeVisible();
    },
  },
  {
    name: 's16-queue-workload',
    setup: async (page) => {
      await page.addInitScript(() => {
        window.localStorage.setItem('clearpath.queue.workload', 'open');
      });
      await stubApi(page, { me: ME.lead });
    },
    path: '/queue',
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Workload by reviewer' })).toBeVisible();
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
    },
  },
  {
    name: 's16-assignee-picker-out-of-office',
    setup: async (page) => {
      await stubApi(page, { me: ME.lead });
      // Registered after stubApi, so it answers /api/users first: Sam is out.
      await page.route(/\/api\/users(\?|$)/, (route) =>
        route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify(USERS.map((u) => (u.id === 3 ? { ...u, is_available: false } : u))),
        }),
      );
    },
    path: '/queue',
    act: async (page) => {
      await page
        .getByRole('button', { name: /^Assignee for CP-/ })
        .first()
        .click();
    },
    ready: async (page) => {
      await expect(page.getByRole('menuitem', { name: /out of office/ })).toBeVisible();
    },
  },
];

for (const shot of shots) {
  test(`${shot.name} @ 1440`, async ({ page }) => {
    await page.setViewportSize(SIZE);
    await shot.setup(page);
    await page.goto(shot.path);
    if (shot.act !== undefined) await shot.act(page);
    await shot.ready(page);
    if (shot.act === undefined) await page.mouse.move(0, SIZE.height - 1);
    await page.waitForTimeout(250);
    await page.screenshot({ path: `${OUT}/${shot.name}-1440.png` });
  });
}
