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
    const first = await screen.findByRole('button', { name: /Time to first review/ });
    expect(first).toHaveTextContent('5.0 h');
    expect(first).toHaveTextContent('p90 30.0 h');
    expect(first).toHaveTextContent('42 items · 30 native · 12 imported');
    expect(first).toHaveTextContent('Native 4.0 h · Imported 9.0 d');
    expect(screen.getByRole('button', { name: /Time per round/ })).toHaveTextContent('native only');
    expect(screen.getByRole('button', { name: /Rounds per item/ })).toHaveTextContent('1.8');
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
    await userEvent.click(await screen.findByRole('button', { name: '2 open now · oldest 3.1 d' }));

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

    await userEvent.click(within(row).getByRole('button', { name: 'Items for Oct 5 – Oct 11' }));
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
      expect(router.state.location.search).toMatchObject({ legacy: false });
    });
    await waitFor(() => {
      const last = requests.filter((url) => url.pathname.endsWith('/metrics/summary')).at(-1);
      expect(last?.searchParams.get('include_legacy')).toBe('false');
    });
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
    expect(await screen.findByText('Metrics are temporarily unavailable.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(await screen.findByRole('table', { name: /Throughput by week/ })).toBeInTheDocument();
  });

  it('renders the chart with a name that says what it compares', async () => {
    renderApp('/metrics');
    expect(
      await screen.findByRole('img', { name: /Throughput by week, native and imported/ }),
    ).toBeInTheDocument();
  });
});
