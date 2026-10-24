import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getListItemsMockHandler } from '../../api/generated/items/items.msw';
import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import type { AttachmentOut, PartnerUpdateIn } from '../../api/generated/model';
import { ApiError } from '../../api/mutator';
import { uploadPartnerAttachment } from '../../api/generated/partners/partners';
import {
  getGetPartnerMockHandler,
  getListPartnerFindingsMockHandler,
} from '../../api/generated/partners/partners.msw';
import {
  LEAD_ME,
  PARTNER_ATTACHMENTS,
  PARTNER_DETAIL,
  PARTNER_FINDINGS_PAGE_1,
  PARTNER_FINDINGS_PAGE_2,
  partnerItemRows,
  REVIEWER_ME,
} from '../../test/fixtures/termsPartners';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

// jsdom's File can't go through undici's multipart encoder, so uploads are asserted at the client call.
vi.mock('../../api/generated/partners/partners', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/generated/partners/partners')>()),
  uploadPartnerAttachment: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(uploadPartnerAttachment).mockReset();
  server.use(
    getGetMeMockHandler(LEAD_ME),
    getGetPartnerMockHandler(PARTNER_DETAIL),
    getListItemsMockHandler({ rows: partnerItemRows(), next_cursor: null, total: 3 }),
    getListPartnerFindingsMockHandler(({ request }) =>
      new URL(request.url).searchParams.get('cursor') === 'page-2'
        ? { rows: PARTNER_FINDINGS_PAGE_2, next_cursor: null }
        : { rows: PARTNER_FINDINGS_PAGE_1, next_cursor: 'page-2' },
    ),
  );
});

describe('Partner detail', () => {
  it('shows the facts, counts, and agreement and evidence', async () => {
    renderApp('/partners/31');
    expect(await screen.findByRole('heading', { name: 'LoanFinder', level: 1 })).toBeInTheDocument();
    const facts = screen.getByRole('region', { name: 'Details' });
    expect(within(facts).getByRole('link', { name: 'loanfinder.example.com' })).toHaveAttribute(
      'href',
      'https://loanfinder.example.com',
    );
    expect(within(facts).getByText('Jan 12, 2026')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '5 Open findings' })).toBeInTheDocument();

    const files = screen.getByRole('region', { name: 'Agreement and evidence' });
    const agreement = within(files).getByRole('listitem', { name: PARTNER_ATTACHMENTS[0]?.original_name });
    expect(
      within(agreement).getByRole('link', { name: PARTNER_ATTACHMENTS[0]?.original_name }),
    ).toHaveAttribute('href', '/api/attachments/901/download');
    expect(agreement).toHaveTextContent('Agreement');
    expect(agreement).toHaveTextContent('sha256 9f2c41d0b7e3');
    expect(agreement).toHaveTextContent('Priya Raman');
  });

  it('lists items newest first and marks legacy imports', async () => {
    renderApp('/partners/31');
    const table = await screen.findByRole('table', { name: 'Items from LoanFinder' });
    const legacy = within(table).getByRole('row', { name: /CP-214/ });
    expect(within(legacy).getByText('Legacy')).toBeInTheDocument();
    expect(within(table).getByRole('link', { name: 'Debt consolidation listicle' })).toHaveAttribute(
      'href',
      '/items/1031',
    );
  });

  it('pages through the findings history from its tab', async () => {
    const { router } = renderApp('/partners/31');
    await userEvent.click(await screen.findByRole('tab', { name: /Findings history/ }));
    await waitFor(() => {
      expect(router.state.location.search).toEqual({ tab: 'findings' });
    });
    const history = await screen.findByRole('list', { name: 'Findings history, newest first' });
    expect(within(history).getAllByRole('listitem')).toHaveLength(3);
    const ai = within(history).getAllByRole('listitem')[1];
    expect(ai).toHaveTextContent('Rate claim may need the full APR range. · Reg Z 1026.24(d)');
    expect(ai).toHaveTextContent('AI suggestion');
    expect(within(history).getAllByRole('link', { name: /CP-1042/ })[0]).toHaveAttribute(
      'href',
      '/items/1042',
    );

    await userEvent.click(screen.getByRole('button', { name: 'Load more' }));
    await waitFor(() => {
      expect(within(history).getAllByRole('listitem')).toHaveLength(4);
    });
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
    expect(within(history).getAllByRole('listitem')[3]).toHaveTextContent('Dismissed');
  });

  it('shows repeat issues with counts, each linking to its findings (P2)', async () => {
    const ruleIds: (string | null)[] = [];
    server.use(
      getListPartnerFindingsMockHandler(({ request }) => {
        const rule = new URL(request.url).searchParams.get('rule_id');
        ruleIds.push(rule);
        return {
          rows: rule === null ? PARTNER_FINDINGS_PAGE_1 : PARTNER_FINDINGS_PAGE_1.slice(0, 1),
          next_cursor: null,
        };
      }),
    );
    const { router } = renderApp('/partners/31?tab=repeat');
    const table = await screen.findByRole('table', { name: 'Repeat issues' });
    const row = within(table).getByRole('row', { name: /Partner content discloses the paid relationship/ });
    expect(row).toHaveTextContent('endorsement.material_connection');
    expect(row).toHaveTextContent('16 CFR 255.5');
    expect(
      within(row)
        .getAllByRole('cell')
        .map((c) => c.textContent),
    ).toEqual(expect.arrayContaining(['7', '5']));

    await userEvent.click(
      within(row).getByRole('link', { name: 'Partner content discloses the paid relationship' }),
    );
    await waitFor(() => {
      expect(router.state.location.search).toEqual({
        tab: 'findings',
        rule: 'endorsement.material_connection',
      });
    });
    const history = await screen.findByRole('list', { name: 'Findings history, newest first' });
    await waitFor(() => {
      expect(within(history).getAllByRole('listitem')).toHaveLength(1);
    });
    expect(ruleIds).toContain('endorsement.material_connection');
    expect(screen.getByRole('status', { name: '' })).toHaveTextContent(
      'Only Partner content discloses the paid relationship',
    );
    await userEvent.click(screen.getByRole('link', { name: 'Show all findings' }));
    await waitFor(() => {
      expect(router.state.location.search).toEqual({ tab: 'findings' });
    });
  });

  it('counts the loaded findings on the tab, "+" when there are more pages (P10)', async () => {
    renderApp('/partners/31');
    expect(await screen.findByRole('tab', { name: 'Findings history 3+' })).toBeInTheDocument();
  });

  it("doesn't offer Retry on a 403: asking again won't change it (P6)", async () => {
    server.use(
      http.get('*/api/partners/31/findings', () =>
        HttpResponse.json(
          { code: 'not_permitted', message: 'Findings history is for reviewers and leads.' },
          { status: 403 },
        ),
      ),
    );
    renderApp('/partners/31?tab=findings');
    expect(await screen.findByText(/Findings history is for reviewers and leads\./)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('says agreements are hidden, not missing, for a role that cannot read them (P6)', async () => {
    server.use(
      getGetMeMockHandler({ ...REVIEWER_ME, roles: ['marketer'], effective_roles: ['marketer'] }),
      getGetPartnerMockHandler({ ...PARTNER_DETAIL, attachments: [] }),
    );
    renderApp('/partners/31');
    const files = await screen.findByRole('region', { name: 'Agreement and evidence' });
    expect(within(files).getByText('Agreements are visible to reviewers and leads.')).toBeInTheDocument();
    expect(within(files).queryByText(/No agreement on file/)).not.toBeInTheDocument();
  });

  it('keeps the page when the findings history fails, with Retry there', async () => {
    server.use(
      http.get('*/api/partners/31/findings', () =>
        HttpResponse.json({ code: 'server_error', message: 'Findings are unavailable.' }, { status: 503 }),
      ),
    );
    renderApp('/partners/31?tab=findings');
    expect(await screen.findByText(/Findings are unavailable\./)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'LoanFinder', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Details' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('uploads an attachment with its kind and refreshes the list', async () => {
    const amendment = { ...PARTNER_ATTACHMENTS[0], id: 950, original_name: 'amendment.pdf' } as AttachmentOut;
    vi.mocked(uploadPartnerAttachment).mockImplementation(() => {
      server.use(
        getGetPartnerMockHandler({ ...PARTNER_DETAIL, attachments: [amendment, ...PARTNER_ATTACHMENTS] }),
      );
      return Promise.resolve(amendment);
    });
    renderApp('/partners/31');
    const files = await screen.findByRole('region', { name: 'Agreement and evidence' });
    const file = new File(['%PDF'], 'amendment.pdf', { type: 'application/pdf' });
    await userEvent.upload(within(files).getByLabelText('File'), file);
    await userEvent.click(within(files).getByRole('button', { name: 'Upload' }));

    expect(await within(files).findByRole('link', { name: 'amendment.pdf' })).toBeInTheDocument();
    expect(vi.mocked(uploadPartnerAttachment)).toHaveBeenCalledWith(31, { kind: 'agreement', file });
  });

  it('says why an upload failed, in one line', async () => {
    vi.mocked(uploadPartnerAttachment).mockRejectedValue(
      new ApiError(403, { code: 'not_permitted', message: 'Only leads upload partner documents.' }),
    );
    renderApp('/partners/31');
    const files = await screen.findByRole('region', { name: 'Agreement and evidence' });
    await userEvent.click(within(files).getByRole('button', { name: 'Upload' }));
    expect(await within(files).findByRole('alert')).toHaveTextContent('Choose a file and its kind.');
    await userEvent.upload(within(files).getByLabelText('File'), new File(['x'], 'a.pdf'));
    await userEvent.click(within(files).getByRole('button', { name: 'Upload' }));
    expect(await within(files).findByText('Only leads upload partner documents.')).toBeInTheDocument();
  });

  it('edits the facts inline for a lead and sends only what changed', async () => {
    let patch: PartnerUpdateIn | undefined;
    server.use(
      http.patch('*/api/partners/31', async ({ request }) => {
        patch = (await request.json()) as PartnerUpdateIn;
        return HttpResponse.json({ ...PARTNER_DETAIL, status: 'paused' });
      }),
    );
    renderApp('/partners/31');
    const facts = await screen.findByRole('region', { name: 'Details' });
    await userEvent.click(within(facts).getByRole('button', { name: 'Edit details' }));
    const form = within(facts).getByRole('form', { name: 'Edit partner details' });
    // Focus moves into the form (P9).
    expect(within(form).getByRole('textbox', { name: /Name/ })).toHaveFocus();
    await userEvent.click(within(form).getByRole('button', { name: /Status/ }));
    await userEvent.click(await screen.findByRole('option', { name: 'Paused' }));
    await userEvent.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(patch).toEqual({ status: 'paused' });
    });
    expect(await screen.findByRole('heading', { name: 'LoanFinder', level: 1 })).toBeInTheDocument();
    expect(within(facts).queryByRole('form')).not.toBeInTheDocument();
    // ... and back to the trigger when it closes.
    expect(within(facts).getByRole('button', { name: 'Edit details' })).toHaveFocus();
  });

  it('is read-only for reviewers', async () => {
    server.use(getGetMeMockHandler(REVIEWER_ME));
    renderApp('/partners/31');
    const facts = await screen.findByRole('region', { name: 'Details' });
    expect(within(facts).queryByRole('button', { name: 'Edit details' })).not.toBeInTheDocument();
    const files = screen.getByRole('region', { name: 'Agreement and evidence' });
    expect(within(files).queryByRole('button', { name: 'Upload' })).not.toBeInTheDocument();
  });

  it('says when the partner does not exist', async () => {
    server.use(
      http.get('*/api/partners/99', () =>
        HttpResponse.json({ code: 'not_found', message: "Partner 99 doesn't exist." }, { status: 404 }),
      ),
    );
    renderApp('/partners/99');
    expect(await screen.findByRole('heading', { name: "Partner 99 doesn't exist" })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'All partners' })).toHaveAttribute('href', '/partners');
  });
});
