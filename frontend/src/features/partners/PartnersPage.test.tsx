import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { getListItemsMockHandler } from '../../api/generated/items/items.msw';
import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import type { PartnerIn } from '../../api/generated/model';
import {
  getGetPartnerMockHandler,
  getListPartnerFindingsMockHandler,
  getListPartnersMockHandler,
} from '../../api/generated/partners/partners.msw';
import {
  LEAD_ME,
  PARTNER_DETAIL,
  PARTNER_ROWS,
  partnerItemRows,
  REVIEWER_ME,
} from '../../test/fixtures/termsPartners';
import { renderApp, searchString } from '../../test/renderApp';
import { server } from '../../test/server';

/** Serves the list, filtered like the backend, and records each request's query. */
function serveList(): URLSearchParams[] {
  const seen: URLSearchParams[] = [];
  server.use(
    getListPartnersMockHandler(({ request }) => {
      const params = new URL(request.url).searchParams;
      seen.push(params);
      const status = params.get('status');
      const q = params.get('q')?.toLowerCase();
      return PARTNER_ROWS.filter(
        (p) =>
          (status === null || p.status === status) && (q === undefined || p.name.toLowerCase().includes(q)),
      );
    }),
  );
  return seen;
}

beforeEach(() => {
  server.use(getGetMeMockHandler(LEAD_ME));
});

describe('Partners list', () => {
  it('lists partners with their counts, sorted as served', async () => {
    serveList();
    renderApp('/partners');
    const table = await screen.findByRole('table', { name: 'Partners' });
    const row = within(table).getByRole('row', { name: /LoanFinder/ });
    expect(within(row).getByRole('link', { name: 'LoanFinder' })).toHaveAttribute('href', '/partners/31');
    expect(within(row).getByText('Affiliate')).toBeInTheDocument();
    expect(within(row).getByText('Active')).toBeInTheDocument();
    expect(
      within(row)
        .getAllByRole('cell')
        .map((c) => c.textContent),
    ).toEqual(expect.arrayContaining(['24', '15', '5']));
    expect(within(table).getByRole('row', { name: /RateRadar/ })).toHaveTextContent('—');
  });

  it('filters by status and name through the URL', async () => {
    const seen = serveList();
    const { router } = renderApp('/partners');
    await screen.findByRole('table', { name: 'Partners' });

    await userEvent.click(screen.getByRole('button', { name: /Status/ }));
    await userEvent.click(await screen.findByRole('option', { name: 'Paused' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ status: 'paused' });
    });
    expect(await screen.findByRole('row', { name: /CreditMatch/ })).toBeInTheDocument();
    expect(screen.queryByRole('row', { name: /LoanFinder/ })).not.toBeInTheDocument();

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search partners' }), 'zzz');
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ status: 'paused', q: 'zzz' });
    });
    expect(seen.at(-1)?.get('q')).toBe('zzz');
    expect(
      await screen.findByRole('heading', { name: 'No partners match these filters' }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    await waitFor(() => {
      expect(router.state.location.search).toEqual({});
    });
  });

  it('reads filters from the URL and ignores bad ones', async () => {
    const seen = serveList();
    renderApp(`/partners${searchString({ status: 'bogus', q: 'loan' })}`);
    expect(await screen.findByRole('row', { name: /LoanFinder/ })).toBeInTheDocument();
    expect(seen.at(-1)?.get('status')).toBeNull();
    expect(screen.getByRole('searchbox', { name: 'Search partners' })).toHaveValue('loan');
  });

  it('lets a lead add a partner, putting a 422 on its field, then opens it', async () => {
    serveList();
    let calls = 0;
    let body: PartnerIn | undefined;
    server.use(
      http.post('*/api/partners', async ({ request }) => {
        calls += 1;
        body = (await request.json()) as PartnerIn;
        return calls === 1
          ? HttpResponse.json(
              {
                code: 'invalid_input',
                message: 'Check the highlighted fields.',
                fields: [{ loc: ['body', 'name'], message: 'A partner named LoanFinder already exists.' }],
              },
              { status: 422 },
            )
          : HttpResponse.json({ ...PARTNER_DETAIL, id: 40, name: 'FundFlow' }, { status: 201 });
      }),
      getGetPartnerMockHandler({ ...PARTNER_DETAIL, id: 40, name: 'FundFlow' }),
      getListItemsMockHandler({ rows: [], next_cursor: null, total: 0 }),
      getListPartnerFindingsMockHandler({ rows: [], next_cursor: null }),
    );
    const { router } = renderApp('/partners');
    await userEvent.click(await screen.findByRole('button', { name: 'New partner' }));
    const form = screen.getByRole('form', { name: 'New partner' });
    await userEvent.type(within(form).getByRole('textbox', { name: 'Name' }), 'LoanFinder');
    await userEvent.click(within(form).getByRole('button', { name: /Type/ }));
    await userEvent.click(await screen.findByRole('option', { name: 'Lead gen' }));
    await userEvent.click(within(form).getByRole('button', { name: 'Add partner' }));

    expect(await within(form).findByText('A partner named LoanFinder already exists.')).toBeInTheDocument();
    const name = within(form).getByRole('textbox', { name: 'Name' });
    await userEvent.clear(name);
    await userEvent.type(name, 'FundFlow');
    await userEvent.click(within(form).getByRole('button', { name: 'Add partner' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/partners/40');
    });
    expect(body).toMatchObject({ name: 'FundFlow', type: 'lead_gen', agreement_signed_on: null });
  });

  it('checks the new partner form before sending', async () => {
    serveList();
    renderApp('/partners');
    await userEvent.click(await screen.findByRole('button', { name: 'New partner' }));
    const form = screen.getByRole('form', { name: 'New partner' });
    await userEvent.type(within(form).getByRole('textbox', { name: 'Contact email' }), 'not-an-email');
    await userEvent.click(within(form).getByRole('button', { name: 'Add partner' }));
    expect(await within(form).findByText('Enter a name.')).toBeInTheDocument();
    expect(within(form).getByText('Choose a type.')).toBeInTheDocument();
    expect(
      within(form).getByText('Enter an email address, e.g. compliance@partner.com.'),
    ).toBeInTheDocument();
  });

  it('hides partner management from reviewers', async () => {
    server.use(getGetMeMockHandler(REVIEWER_ME));
    serveList();
    renderApp('/partners');
    await screen.findByRole('table', { name: 'Partners' });
    expect(screen.queryByRole('button', { name: 'New partner' })).not.toBeInTheDocument();
  });

  it('says why the list is empty, and shows a load error with Retry', async () => {
    server.use(getListPartnersMockHandler([]));
    const { unmount } = renderApp('/partners');
    expect(await screen.findByRole('heading', { name: 'No partners yet' })).toBeInTheDocument();
    unmount();

    server.use(
      http.get('*/api/partners', () =>
        HttpResponse.json({ code: 'server_error', message: 'Partners are unavailable.' }, { status: 503 }),
      ),
    );
    renderApp('/partners');
    expect(await screen.findByText(/Partners are unavailable\./)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('items served for a partner', () => {
  it('asks for every status, newest first (legacy included)', async () => {
    let params: URLSearchParams | undefined;
    server.use(
      getGetPartnerMockHandler(PARTNER_DETAIL),
      getListItemsMockHandler(({ request }) => {
        params = new URL(request.url).searchParams;
        return { rows: partnerItemRows(), next_cursor: null, total: 3 };
      }),
      getListPartnerFindingsMockHandler({ rows: [], next_cursor: null }),
    );
    renderApp('/partners/31');
    await screen.findByRole('table', { name: 'Items from LoanFinder' });
    expect(params?.getAll('partner_id')).toEqual(['31']);
    expect(params?.get('sort')).toBe('newest');
    expect(params?.has('status')).toBe(false);
  });
});
