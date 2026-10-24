import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import {
  getGetMetricSeriesMockHandler,
  getGetMetricsSummaryMockHandler,
  getListMetricItemsMockHandler,
} from '../../api/generated/metrics/metrics.msw';
import { getListPartnersMockHandler } from '../../api/generated/partners/partners.msw';
import { renderApp, searchString } from '../../test/renderApp';
import { server } from '../../test/server';
import { EMPTY_SERIES, EMPTY_SUMMARY, ITEMS, ME_LEAD, PARTNERS, SERIES, SUMMARY } from './fixtures';

const requests: URL[] = [];

beforeEach(() => {
  requests.length = 0;
  server.use(
    getGetMeMockHandler(ME_LEAD),
    getListPartnersMockHandler(PARTNERS),
    getGetMetricsSummaryMockHandler(({ request }) => {
      requests.push(new URL(request.url));
      return SUMMARY;
    }),
    getGetMetricSeriesMockHandler(SERIES),
    getListMetricItemsMockHandler(({ request }) => {
      requests.push(new URL(request.url));
      return ITEMS;
    }),
  );
});

function table(search: Record<string, unknown> = {}) {
  return renderApp(`/metrics${searchString({ view: 'table', ...search })}`);
}

describe('MetricsPage', () => {
  it('shows each headline number with where it came from', async () => {
    table();
    // Both sources: each source's own median at equal weight, no blended headline.
    const first = await screen.findByRole('button', { name: /Time to first review/ });
    expect(first).toHaveTextContent('4.0 h native');
    expect(first).toHaveTextContent('9.0 d imported');
    expect(first).not.toHaveTextContent('5.0 h');
    expect(first).toHaveTextContent('42 items· 30 native· 12 imported');
    // One source: the figure, with p90 once there are enough measurements.
    const rounds = screen.getByRole('button', { name: /Time per round/ });
    expect(rounds).toHaveTextContent('7.5 h');
    expect(rounds).toHaveTextContent('median · p90 2.2 d');
    expect(rounds).toHaveTextContent('native only');
    // Few measurements: no p90.
    expect(screen.getByRole('button', { name: /Time to fix live content/ })).not.toHaveTextContent('p90');
    expect(screen.getByRole('button', { name: /Rounds per item/ })).toHaveTextContent('1.4 native');
    expect(screen.getByRole('button', { name: /Throughput/ })).toHaveTextContent('64');
    expect(screen.getByRole('button', { name: /Throughput/ })).toHaveTextContent('4.9 per week');
    expect(
      screen.getByText(/Imported tracker history covers Jan 6, 2025 – Aug 14, 2026/),
    ).toBeInTheDocument();
  });

  it('asks for the 13 weeks ending today by default', async () => {
    table();
    await screen.findByRole('button', { name: /Time to first review/ });
    const summary = requests.find((url) => url.pathname.endsWith('/metrics/summary'));
    expect(summary?.searchParams.get('period_from')).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(summary?.searchParams.has('include_legacy')).toBe(false);
  });

  it('opens the items behind a number, linking each to its review', async () => {
    const { router } = table();
    await userEvent.click(await screen.findByRole('button', { name: /Time to first review/ }));

    const drill = await screen.findByRole('region', { name: /Time to first review/ });
    expect(within(drill).getByText('2 items')).toBeInTheDocument();
    const imported = within(drill).getByRole('row', { name: /CP-17/ });
    expect(imported).toHaveTextContent('Imported · MCR-25-031');
    expect(imported).toHaveTextContent('3.0 d');
    expect(within(drill).getByRole('link', { name: 'Spring PL email' })).toHaveAttribute(
      'href',
      '/items/1042',
    );
    expect(router.state.location.search).toMatchObject({ drill: 'time_to_first_review' });
  });

  it('opens the still-open fix-live clocks from the alert', async () => {
    const { router } = table();
    await userEvent.click(await screen.findByRole('button', { name: '2 re-reviews open · oldest 3.1 d' }));

    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ drill: 'time_to_fix_live', open: true });
    });
    await waitFor(() => {
      const call = requests.find((url) => url.pathname.endsWith('/metrics/items'));
      expect(call?.searchParams.get('open_only')).toBe('true');
    });
  });

  it('links each waiting count to the queue view with the same filters', async () => {
    table({ product: 'credit_card' });
    const link = await screen.findByRole('link', { name: 'More than 7 days: 4' });
    const href = new URL(link.getAttribute('href') ?? '', 'http://x');
    expect(href.pathname).toBe('/');
    expect(href.searchParams.get('waiting')).toBe('7');
    expect(href.searchParams.get('product')).toBe('["credit_card"]');
  });

  it('lists the trend as a table whose rows open that bucket', async () => {
    const { router } = table();
    const trend = await screen.findByRole('table', { name: /Throughput by week/ });
    const row = within(trend).getByRole('row', { name: /Oct 5/ });
    expect(row).toHaveTextContent('4 native · 2 imported');

    await userEvent.click(within(row).getByRole('button', { name: /^Items for Oct 5/ }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({
        drill: 'throughput',
        dfrom: '2026-10-05',
        dto: '2026-10-11',
      });
    });
  });

  it('narrows to native data and says so', async () => {
    const { router } = table();
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Include imported history' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ imported: false });
    });
    await waitFor(() => {
      const last = requests.filter((url) => url.pathname.endsWith('/metrics/summary')).at(-1);
      expect(last?.searchParams.get('include_legacy')).toBe('false');
    });
    expect(screen.getByText('Native data only: imported tracker history is excluded.')).toBeInTheDocument();
    expect(screen.queryByText(/Imported: the final decision only/)).not.toBeInTheDocument();
  });

  it('switches to the imported history range in one click', async () => {
    const { router } = table();
    await userEvent.click(await screen.findByRole('button', { name: 'Show that period' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({
        range: 'custom',
        from: '2025-01-06',
        to: '2026-08-14',
      });
    });
  });

  it('says why the period is empty and offers a wider one', async () => {
    server.use(getGetMetricsSummaryMockHandler(EMPTY_SUMMARY), getGetMetricSeriesMockHandler(EMPTY_SERIES));
    table({ range: '4w' });
    expect(await screen.findByRole('heading', { name: 'No decisions in this period' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Last 12 months' })).toBeInTheDocument();
  });

  it('keeps the trend usable when the summary fails', async () => {
    server.use(
      http.get('*/api/metrics/summary', () =>
        HttpResponse.json(
          { code: 'server_error', message: 'Metrics are temporarily unavailable.' },
          { status: 503 },
        ),
      ),
    );
    table();
    expect(
      await screen.findByText(/Couldn.t load the headline numbers\. Metrics are temporarily unavailable\./),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(await screen.findByRole('table', { name: /Throughput by week/ })).toBeInTheDocument();
  });

  it('shows a refusal at once, without a Retry that cannot succeed', async () => {
    server.use(
      http.get('*/api/metrics/summary', () =>
        HttpResponse.json(
          { code: 'invalid_input', message: 'The period starts after it ends.', details: {}, fields: [] },
          { status: 422 },
        ),
      ),
    );
    table();
    expect(await screen.findByText(/The period starts after it ends\./)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('applies a custom period only when it is complete and in order', async () => {
    const { router } = table({ range: 'custom', from: '2026-03-01', to: '2026-03-31' });
    const from = await screen.findByLabelText('From');
    const to = screen.getByLabelText('To');

    await userEvent.clear(to);
    await userEvent.type(to, '2026-02-01');
    expect(await screen.findByText('Ends before it starts.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
    expect(router.state.location.search).toMatchObject({ from: '2026-03-01', to: '2026-03-31' });

    await userEvent.clear(to);
    await userEvent.type(to, '2026-04-15{Enter}');
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ from: '2026-03-01', to: '2026-04-15' });
    });
    expect(from).toHaveValue('2026-03-01');
  });

  it('never sends a backwards period from a hand-edited URL', async () => {
    table({ range: 'custom', from: '2026-10-24', to: '2026-01-01' });
    expect(await screen.findByText(/The period ends before it starts/)).toBeInTheDocument();
    expect(requests.filter((url) => url.pathname.endsWith('/metrics/summary'))).toHaveLength(0);
  });

  it('returns focus to the tile that opened the list when it closes', async () => {
    table();
    const tile = await screen.findByRole('button', { name: /Throughput/ });
    expect(tile).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(tile);
    expect(tile).toHaveAttribute('aria-expanded', 'true');
    expect(tile).toHaveAttribute('aria-controls', 'metric-drill');

    await userEvent.click(await screen.findByRole('button', { name: 'Close the item list' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Throughput/ })).toHaveFocus();
    });
  });

  it('offers to clear the filters when they emptied the page', async () => {
    server.use(getGetMetricsSummaryMockHandler(EMPTY_SUMMARY), getGetMetricSeriesMockHandler(EMPTY_SERIES));
    const { router } = table({ partner: 4 });
    expect(await screen.findByText(/has no decisions for these filters/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Trend' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    await waitFor(() => {
      expect(router.state.location.search).not.toHaveProperty('partner');
    });
  });

  it('renders the chart with a name that says what it compares', async () => {
    renderApp('/metrics');
    expect(
      await screen.findByRole('img', { name: /Throughput by week, native and imported/ }),
    ).toBeInTheDocument();
  });
});
