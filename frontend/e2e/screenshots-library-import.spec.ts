/*
 * UI-review screenshots of every Library and Import state (spec §8.4). Skipped unless SCREENSHOTS=1:
 *   SCREENSHOTS=1 E2E_PORT=4392 npx playwright test e2e/screenshots-library-import.spec.ts
 * Output: docs/plan/reviews/ui/screens/<library|import>-<state>-<width>.png
 */
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

import {
  CUSTOM_COUNTS,
  CUSTOM_PROBLEMS,
  CUSTOM_ROWS,
  CUSTOM_UNMAPPED,
  importJob,
  importPreview,
} from '../src/test/fixtures/imports';
import {
  APPROVED_ROWS,
  libraryRow,
  ME_LIBRARY_MARKETER,
  ME_LIBRARY_REVIEWER,
} from '../src/test/fixtures/library';
import { stubLibraryApi } from './libraryImportApi';
import type { LibraryStubOptions } from './libraryImportApi';

const OUT = '../docs/plan/reviews/ui/screens';
/** Failed reads retry three times with backoff (React Query's default) before the error state shows. */
const RETRIES = { timeout: 15_000 };
const SIZES = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
] as const;

test.skip(process.env.SCREENSHOTS !== '1', 'set SCREENSHOTS=1 to capture UI-review screenshots');

interface Shot {
  name: string;
  path: string;
  stub?: LibraryStubOptions;
  act?: (page: Page) => Promise<void>;
  ready: (page: Page) => Promise<void>;
}

const PRECEDENTS = "/library?tab=precedents&query=won't%20affect%20your%20credit%20score";
const MANY_ROWS = [
  ...APPROVED_ROWS,
  ...Array.from({ length: 14 }, (_, i) =>
    libraryRow({
      id: 1000 - i,
      title:
        ['Card welcome email series — step 2', 'PL retargeting display banner', 'Prequal SMS reminder'][
          i % 3
        ] ?? '',
      product: (['credit_card', 'personal_loan', 'mortgage_prequal'] as const)[i % 3],
      channel: (['email', 'display', 'sms'] as const)[i % 3],
    }),
  ),
];

const shots: Shot[] = [
  // ---- Library: approved to run ----
  {
    name: 'library-approved',
    path: '/library',
    stub: { me: ME_LIBRARY_REVIEWER, library: MANY_ROWS },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Approved to run' })).toBeVisible();
    },
  },
  {
    name: 'library-approved-loading',
    path: '/library',
    stub: { me: ME_LIBRARY_REVIEWER, library: 'hang' },
    ready: async (page) => {
      await expect(page.getByRole('status', { name: 'Loading the library' })).toBeVisible();
    },
  },
  {
    name: 'library-approved-empty',
    path: '/library',
    stub: { me: ME_LIBRARY_REVIEWER, library: [] },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: 'Nothing is approved to run' })).toBeVisible();
    },
  },
  {
    name: 'library-approved-empty-filtered',
    path: '/library?channel=%5B%22sms%22%5D&legacy=exclude',
    stub: { me: ME_LIBRARY_REVIEWER, library: [] },
    ready: async (page) => {
      await expect(
        page.getByRole('heading', { name: 'No approved items match these filters' }),
      ).toBeVisible();
    },
  },
  {
    name: 'library-approved-error',
    path: '/library',
    stub: { me: ME_LIBRARY_REVIEWER, library: 503 },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: "Couldn't load the library" })).toBeVisible(RETRIES);
    },
  },
  {
    name: 'library-approved-partial',
    path: '/library',
    stub: { me: ME_LIBRARY_REVIEWER, library: APPROVED_ROWS, morePages: 503 },
    act: async (page) => {
      await page.getByRole('button', { name: 'Load more' }).click();
    },
    ready: async (page) => {
      await expect(page.getByText("Couldn't load more items. Try again.")).toBeVisible(RETRIES);
    },
  },
  {
    name: 'library-filters-date',
    path: '/library?approved_from=2026-07-01&approved_to=2026-09-30&product=%5B%22credit_card%22%5D',
    stub: { me: ME_LIBRARY_REVIEWER, library: APPROVED_ROWS.slice(1, 2) },
    act: async (page) => {
      await page.getByRole('button', { name: /Approved: Jul 1, 2026/ }).click();
    },
    ready: async (page) => {
      await expect(page.getByRole('dialog', { name: 'Approved' })).toBeVisible();
    },
  },
  {
    name: 'library-export-menu',
    path: '/library',
    stub: { me: ME_LIBRARY_REVIEWER },
    act: async (page) => {
      await page.getByRole('button', { name: 'Export' }).click();
    },
    ready: async (page) => {
      await expect(page.getByRole('menuitem', { name: /with evidence packs/ })).toBeVisible();
    },
  },
  {
    name: 'library-export-running',
    path: '/library',
    stub: { me: ME_LIBRARY_REVIEWER, exportOutcome: 'running' },
    act: async (page) => {
      await page.getByRole('button', { name: 'Export' }).click();
      await page.getByRole('menuitem', { name: /Export view \(\.xlsx\)/ }).click();
    },
    ready: async (page) => {
      await expect(page.getByText('Building export…')).toBeVisible();
    },
  },
  {
    name: 'library-export-ready',
    path: '/library',
    stub: { me: ME_LIBRARY_REVIEWER, packRefused: [1081] },
    act: async (page) => {
      await page.getByRole('button', { name: 'Export' }).click();
      await page.getByRole('menuitem', { name: /Export view \(\.xlsx\)/ }).click();
      await page.getByRole('button', { name: 'Build pack for CP-1088' }).click();
      await page.getByRole('button', { name: 'Build pack for CP-1081' }).click();
    },
    ready: async (page) => {
      await expect(page.getByRole('link', { name: 'Download', exact: true })).toBeVisible();
      await expect(page.getByRole('link', { name: 'Download evidence pack for CP-1088' })).toBeVisible();
      await expect(
        page.getByText('CP-1081 has no approval yet; an evidence pack records one.'),
      ).toBeVisible();
    },
  },
  {
    name: 'library-export-failed',
    path: '/library',
    stub: { me: ME_LIBRARY_REVIEWER, exportOutcome: 'failed' },
    act: async (page) => {
      await page.getByRole('button', { name: 'Export' }).click();
      await page.getByRole('menuitem', { name: /with evidence packs/ }).click();
    },
    ready: async (page) => {
      await expect(page.getByText('The export ran out of time. Try a narrower view.')).toBeVisible();
    },
  },
  {
    name: 'library-marketer',
    path: '/library',
    stub: { me: ME_LIBRARY_MARKETER },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Approved to run' })).toBeVisible();
    },
  },
  // ---- Library: precedents ----
  {
    name: 'library-precedents-idle',
    path: '/library?tab=precedents',
    stub: { me: ME_LIBRARY_REVIEWER },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: 'Search precedents' })).toBeVisible();
    },
  },
  {
    name: 'library-precedents',
    path: PRECEDENTS,
    stub: { me: ME_LIBRARY_REVIEWER },
    ready: async (page) => {
      await expect(page.getByRole('list', { name: 'Precedents' })).toBeVisible();
    },
  },
  {
    name: 'library-precedents-text',
    path: `${PRECEDENTS.replace("won't%20affect%20your%20credit%20score", 'credit%20score%20-guaranteed')}&mode=text`,
    stub: { me: ME_LIBRARY_REVIEWER },
    ready: async (page) => {
      await expect(page.getByRole('list', { name: 'Precedents' })).toBeVisible();
    },
  },
  {
    name: 'library-precedents-loading',
    path: PRECEDENTS,
    stub: { me: ME_LIBRARY_REVIEWER, hits: 'hang' },
    ready: async (page) => {
      await expect(page.getByRole('status', { name: 'Searching precedents' })).toBeVisible();
    },
  },
  {
    name: 'library-precedents-empty',
    path: '/library?tab=precedents&query=pre-approved%20today',
    stub: { me: ME_LIBRARY_REVIEWER, hits: [] },
    ready: async (page) => {
      await expect(page.getByRole('button', { name: 'Try text mode' })).toBeVisible();
    },
  },
  {
    name: 'library-precedents-error',
    path: PRECEDENTS,
    stub: { me: ME_LIBRARY_REVIEWER, hits: 503 },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: "Couldn't search precedents" })).toBeVisible(RETRIES);
    },
  },
  // ---- Import ----
  {
    name: 'import-start',
    path: '/import',
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Recent imports' })).toBeVisible();
    },
  },
  {
    name: 'import-start-loading',
    path: '/import',
    stub: { recent: 'hang' },
    ready: async (page) => {
      await expect(page.getByRole('status', { name: 'Loading recent imports' })).toBeVisible();
    },
  },
  {
    name: 'import-start-empty',
    path: '/import',
    stub: { recent: [] },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: 'No imports yet' })).toBeVisible();
    },
  },
  {
    name: 'import-start-partial',
    path: '/import',
    stub: { recent: 503 },
    ready: async (page) => {
      await expect(page.getByText("Couldn't load recent imports.")).toBeVisible(RETRIES);
    },
  },
  {
    name: 'import-not-admin',
    path: '/import',
    stub: { me: ME_LIBRARY_REVIEWER },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: 'Import is for admins' })).toBeVisible();
    },
  },
  {
    name: 'import-columns',
    path: '/import?job=7',
    stub: { job: importJob() },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Column mapping' })).toBeVisible();
    },
  },
  {
    name: 'import-values',
    path: '/import?job=7',
    stub: {
      job: importJob({ status: 'mapped', filename: 'partner-tracker-2025.xlsx', row_count: 42 }),
      preview: importPreview({
        unmapped: CUSTOM_UNMAPPED,
        problems: CUSTOM_PROBLEMS,
        rows: CUSTOM_ROWS,
        counts: CUSTOM_COUNTS,
      }),
    },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Value mapping' })).toBeVisible();
    },
  },
  {
    name: 'import-preview',
    path: '/import?job=7&step=preview',
    stub: { job: importJob({ status: 'mapped' }) },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: 'Preview' })).toBeVisible();
    },
  },
  {
    name: 'import-preview-errors',
    path: '/import?job=7&step=preview',
    stub: {
      job: importJob({ status: 'mapped', filename: 'partner-tracker-2025.xlsx', row_count: 42 }),
      preview: importPreview({
        problems: CUSTOM_PROBLEMS,
        rows: CUSTOM_ROWS,
        unmapped: CUSTOM_UNMAPPED,
        counts: CUSTOM_COUNTS,
      }),
    },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Errors' })).toBeVisible();
    },
  },
  {
    name: 'import-committing',
    path: '/import?job=7',
    stub: { job: importJob({ status: 'committing' }), commitPolls: 10_000 },
    ready: async (page) => {
      await expect(page.getByText(/Importing/).first()).toBeVisible();
    },
  },
  {
    name: 'import-summary',
    path: '/import?job=7&step=preview',
    stub: { job: importJob({ status: 'mapped' }), commitPolls: 1 },
    act: async (page) => {
      await page.getByRole('button', { name: 'Import 178 items' }).click();
    },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Imported items' })).toBeVisible();
    },
  },
  {
    name: 'import-failed',
    path: '/import?job=7',
    stub: {
      job: importJob({
        status: 'failed',
        error: 'The import stopped at row 31: the database was unavailable. Try again.',
      }),
      preview: importPreview({ status: 'failed' }),
    },
    ready: async (page) => {
      await expect(page.getByRole('button', { name: 'Try the import again' })).toBeVisible();
    },
  },
];

for (const size of SIZES) {
  for (const shot of shots) {
    test(`${shot.name} @ ${String(size.width)}`, async ({ page }) => {
      await page.setViewportSize(size);
      await stubLibraryApi(page, shot.stub);
      await page.goto(shot.path);
      if (shot.act !== undefined) await shot.act(page);
      await shot.ready(page);
      await page.mouse.move(0, size.height - 1);
      // Let popover and menu fade-ins (100-160ms) finish so the capture isn't mid-transition.
      await page.waitForTimeout(250);
      await page.screenshot({ path: `${OUT}/${shot.name}-${String(size.width)}.png` });
    });
  }
}
