/*
 * UI-review screenshots of every Offer terms and Partners state (spec §8.4). Skipped unless SCREENSHOTS=1:
 *   SCREENSHOTS=1 E2E_PORT=4393 npx playwright test e2e/screenshots-terms-partners.spec.ts
 * Output: docs/plan/reviews/ui/screens/<terms|partners>-<state>-<width>.png
 */
import { expect as baseExpect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

import { PARTNER_DETAIL, PL_V12, REVIEWER_ME } from '../src/test/fixtures/termsPartners';
import { stubTermsPartners } from './termsPartnersApi.ts';
import type { TermsPartnersStub } from './termsPartnersApi.ts';

// Error states appear after the app's query retries (three, with backoff), so allow for them.
const expect = baseExpect.configure({ timeout: 15_000 });

const OUT = '../docs/plan/reviews/ui/screens';
const SIZES = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
] as const;

test.skip(process.env.SCREENSHOTS !== '1', 'set SCREENSHOTS=1 to capture UI-review screenshots');

interface Shot {
  name: string;
  path: string;
  stub?: TermsPartnersStub;
  ready: (page: Page) => Promise<void>;
}

async function editTerms(page: Page, apr?: string) {
  await page.getByRole('button', { name: 'Edit terms' }).click();
  if (apr !== undefined) {
    await page.getByRole('textbox', { name: 'APR min' }).fill(apr);
  }
}

const shots: Shot[] = [
  {
    name: 'terms-personal-loan',
    path: '/terms',
    ready: async (page) => {
      await expect(page.getByRole('list', { name: 'Personal loan version history' })).toBeVisible();
    },
  },
  {
    name: 'terms-credit-card',
    path: '/terms?product=credit_card',
    ready: async (page) => {
      await expect(page.getByText('Coastal Community Bank')).toBeVisible();
    },
  },
  {
    name: 'terms-mortgage',
    path: '/terms?product=mortgage_prequal',
    ready: async (page) => {
      await expect(
        page.getByRole('heading', { name: 'Mortgage prequalification has no rate terms' }),
      ).toBeVisible();
    },
  },
  {
    name: 'terms-loading',
    path: '/terms',
    stub: { current: 'hang' },
    ready: async (page) => {
      await expect(page.getByRole('status', { name: 'Loading offer terms' })).toBeVisible();
    },
  },
  {
    name: 'terms-error',
    path: '/terms',
    stub: { current: 503 },
    ready: async (page) => {
      await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
    },
  },
  {
    name: 'terms-history-error',
    path: '/terms',
    stub: { history: 503 },
    ready: async (page) => {
      await expect(page.getByText(/Version history didn.t load/)).toBeVisible();
    },
  },
  {
    name: 'terms-empty',
    path: '/terms',
    stub: { current: [], history: [] },
    ready: async (page) => {
      await expect(page.getByRole('button', { name: 'Publish first terms' })).toBeVisible();
    },
  },
  {
    name: 'terms-readonly-reviewer',
    path: '/terms',
    stub: { me: REVIEWER_ME },
    ready: async (page) => {
      await expect(page.getByRole('list', { name: 'Personal loan version history' })).toBeVisible();
    },
  },
  {
    name: 'terms-edit-unchanged',
    path: '/terms',
    ready: async (page) => {
      await editTerms(page);
      await expect(page.getByText("Nothing changed yet: these are v12's values.")).toBeVisible();
    },
  },
  {
    name: 'terms-edit-checking',
    path: '/terms',
    stub: { preview: 'hang' },
    ready: async (page) => {
      await editTerms(page, '12.99');
      await expect(page.getByRole('status', { name: 'Checking the impact' })).toBeVisible();
    },
  },
  {
    name: 'terms-edit-preview',
    path: '/terms',
    ready: async (page) => {
      await editTerms(page, '12.99');
      await expect(page.getByRole('table', { name: 'Affected items' })).toBeAttached();
      await expect(page.getByRole('button', { name: /Publish v13/ })).toBeEnabled();
    },
  },
  {
    name: 'terms-edit-preview-items',
    path: '/terms',
    ready: async (page) => {
      await editTerms(page, '12.99');
      const table = page.getByRole('table', { name: 'Affected items' });
      await table.scrollIntoViewIfNeeded();
      await expect(table).toBeVisible();
    },
  },
  {
    name: 'terms-edit-invalid',
    path: '/terms',
    ready: async (page) => {
      await editTerms(page);
      await page.getByRole('textbox', { name: 'APR max' }).fill('5');
      await page.keyboard.press('Tab');
      await expect(page.getByText('APR max must be at least APR min.')).toBeVisible();
    },
  },
  {
    name: 'terms-edit-min-over-max',
    path: '/terms',
    ready: async (page) => {
      await editTerms(page, '40');
      await expect(page.getByText('APR min must be at most APR max.')).toBeVisible();
      await expect(page.getByText('Fix the highlighted fields to preview the impact.')).toBeVisible();
    },
  },
  {
    name: 'terms-edit-retyping',
    path: '/terms',
    ready: async (page) => {
      await editTerms(page, '12.99');
      await expect(page.getByRole('button', { name: /Publish v13/ })).toBeEnabled();
      await page.getByRole('textbox', { name: 'APR min' }).fill('');
      await expect(page.getByRole('region', { name: /Impact of publishing/ })).toHaveAttribute(
        'aria-busy',
        'true',
      );
    },
  },
  {
    name: 'terms-edit-rebased',
    path: '/terms',
    stub: {
      publishConflict: {
        ...PL_V12,
        id: 113,
        version: 13,
        created_by_name: 'Sam Okafor',
        values: { ...PL_V12.values, apr_max: '29.99' } as typeof PL_V12.values,
      },
    },
    ready: async (page) => {
      await editTerms(page, '12.99');
      const publish = page.getByRole('button', { name: /Publish v13/ });
      await expect(publish).toBeEnabled();
      await publish.click();
      await page
        .getByRole('alertdialog', { name: 'Publish personal loan terms v13?' })
        .getByRole('button', { name: 'Publish v13' })
        .click();
      await expect(page.getByText(/v13 was published since you opened this/)).toBeVisible();
      await expect(page.getByRole('textbox', { name: 'APR max' })).toHaveValue('29.99');
      await expect(page.getByRole('button', { name: 'Publish v14…' })).toBeEnabled();
    },
  },
  {
    name: 'terms-edit-locked-tabs',
    path: '/terms',
    ready: async (page) => {
      await editTerms(page, '12.99');
      await expect(
        page.getByText('Publish or cancel your personal loan edits to switch products.'),
      ).toBeVisible();
      await expect(page.getByRole('table', { name: 'Affected items' })).toBeAttached();
    },
  },
  {
    name: 'terms-edit-preview-error',
    path: '/terms',
    stub: { preview: 503 },
    ready: async (page) => {
      await editTerms(page, '12.99');
      await expect(page.getByText(/Couldn.t preview the impact/)).toBeVisible();
    },
  },
  {
    name: 'terms-confirm',
    path: '/terms',
    ready: async (page) => {
      await editTerms(page, '12.99');
      const publish = page.getByRole('button', { name: /Publish v13/ });
      await expect(publish).toBeEnabled();
      await publish.click();
      await expect(page.getByRole('alertdialog', { name: 'Publish personal loan terms v13?' })).toBeVisible();
    },
  },
  {
    name: 'terms-edit-credit-card',
    path: '/terms?product=credit_card',
    ready: async (page) => {
      await editTerms(page);
      await page.getByRole('textbox', { name: 'Annual fee' }).fill('95');
      await expect(page.getByRole('region', { name: 'Impact of publishing v5' })).toBeVisible();
    },
  },
  {
    name: 'partners-list',
    path: '/partners',
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Partners' })).toBeVisible();
    },
  },
  {
    name: 'partners-loading',
    path: '/partners',
    stub: { partners: 'hang' },
    ready: async (page) => {
      await expect(page.getByRole('status', { name: 'Loading partners' })).toBeVisible();
    },
  },
  {
    name: 'partners-empty',
    path: '/partners',
    stub: { partners: [] },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: 'No partners yet' })).toBeVisible();
    },
  },
  {
    name: 'partners-filtered-empty',
    path: '/partners?status=paused&q=zzz',
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: 'No partners match these filters' })).toBeVisible();
    },
  },
  {
    name: 'partners-error',
    path: '/partners',
    stub: { partners: 503 },
    ready: async (page) => {
      await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
    },
  },
  {
    name: 'partners-create',
    path: '/partners',
    ready: async (page) => {
      await page.getByRole('button', { name: 'New partner' }).click();
      await page.getByRole('button', { name: 'Add partner' }).click();
      await expect(page.getByText('Enter a name.')).toBeVisible();
    },
  },
  {
    name: 'partners-detail-items',
    path: '/partners/31',
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Items from LoanFinder' })).toBeVisible();
    },
  },
  {
    name: 'partners-detail-findings',
    path: '/partners/31?tab=findings',
    ready: async (page) => {
      await expect(page.getByRole('list', { name: 'Findings history, newest first' })).toBeVisible();
    },
  },
  {
    name: 'partners-detail-findings-rule',
    path: '/partners/31?tab=findings&rule=endorsement.material_connection',
    ready: async (page) => {
      await expect(page.getByText('Show all findings')).toBeVisible();
      await expect(page.getByRole('list', { name: 'Findings history, newest first' })).toBeVisible();
    },
  },
  {
    name: 'partners-detail-findings-forbidden',
    path: '/partners/31?tab=findings',
    stub: { findings: 403 },
    ready: async (page) => {
      await expect(page.getByText(/Findings are for reviewers and leads/)).toBeVisible();
    },
  },
  {
    name: 'partners-detail-marketer',
    path: '/partners/31',
    stub: {
      me: { ...REVIEWER_ME, roles: ['marketer'], effective_roles: ['marketer'] },
      partner: { ...PARTNER_DETAIL, attachments: [] },
    },
    ready: async (page) => {
      await expect(page.getByText('Agreements are visible to reviewers and leads.')).toBeVisible();
    },
  },
  {
    name: 'partners-detail-repeat',
    path: '/partners/31?tab=repeat',
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Repeat issues' })).toBeVisible();
    },
  },
  {
    name: 'partners-detail-edit',
    path: '/partners/31',
    ready: async (page) => {
      await page.getByRole('button', { name: 'Edit details' }).click();
      await expect(page.getByRole('form', { name: 'Edit partner details' })).toBeVisible();
    },
  },
  {
    name: 'partners-detail-loading',
    path: '/partners/31',
    stub: { partner: 'hang' },
    ready: async (page) => {
      await expect(page.getByRole('status', { name: 'Loading partner' })).toBeVisible();
    },
  },
  {
    name: 'partners-detail-items-loading',
    path: '/partners/31',
    stub: { items: 'hang' },
    ready: async (page) => {
      await expect(page.getByRole('status', { name: 'Loading items' })).toBeVisible();
    },
  },
  {
    name: 'partners-detail-findings-error',
    path: '/partners/31?tab=findings',
    stub: { findings: 503 },
    ready: async (page) => {
      await expect(page.getByText(/Findings history didn.t load/)).toBeVisible();
    },
  },
  {
    name: 'partners-detail-empty',
    path: '/partners/31',
    stub: {
      items: [],
      findings: [],
      partner: {
        ...PARTNER_DETAIL,
        attachments: [],
        repeat_issues: [],
        item_count: 0,
        approved_count: 0,
        open_findings_count: 0,
        last_submitted_at: null,
        notes: '',
        website: '',
        contact_email: '',
        agreement_signed_on: null,
      },
    },
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: 'No items from LoanFinder yet' })).toBeVisible();
    },
  },
  {
    name: 'partners-detail-reviewer',
    path: '/partners/31',
    stub: { me: REVIEWER_ME },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Items from LoanFinder' })).toBeVisible();
    },
  },
  {
    name: 'partners-detail-not-found',
    path: '/partners/99',
    ready: async (page) => {
      await expect(page.getByRole('heading', { name: "Partner 99 doesn't exist" })).toBeVisible();
    },
  },
];

for (const shot of shots) {
  for (const size of SIZES) {
    test(`${shot.name} ${String(size.width)}`, async ({ page }) => {
      await page.setViewportSize(size);
      await stubTermsPartners(page, shot.stub);
      await page.goto(shot.path);
      await shot.ready(page);
      await page.mouse.move(0, size.height - 1);
      await page.screenshot({
        path: `${OUT}/${shot.name}-${String(size.width)}.png`,
        animations: 'disabled',
      });
    });
  }
}
