/* Stubbed metrics API for the e2e flow and the UI-review screenshots (no backend). */
import type { Page, Route } from '@playwright/test';

import {
  EMPTY_SERIES,
  EMPTY_SUMMARY,
  ITEMS,
  ME_LEAD,
  PARTNERS,
  SERIES,
  SUMMARY,
} from '../src/features/metrics/fixtures';

export type MetricsStub = 'data' | 'empty' | 'loading' | 'error' | 'partial';

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

const hang = () => new Promise<never>(() => undefined);

const FAILURE = {
  code: 'server_error',
  message: 'Metrics are temporarily unavailable.',
  details: {},
  fields: [],
};

export async function stubMetrics(page: Page, mode: MetricsStub = 'data'): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, '');
    if (path === '/me') return json(route, ME_LEAD);
    if (path === '/health') return json(route, { status: 'ok', database: 'ok' });
    if (path === '/partners') return json(route, PARTNERS);
    if (path === '/metrics/summary') {
      if (mode === 'loading') return hang();
      if (mode === 'error' || mode === 'partial') return json(route, FAILURE, 503);
      return json(route, mode === 'empty' ? EMPTY_SUMMARY : SUMMARY);
    }
    if (path === '/metrics/series') {
      if (mode === 'loading') return hang();
      if (mode === 'error') return json(route, FAILURE, 503);
      return json(route, mode === 'empty' ? EMPTY_SERIES : SERIES);
    }
    if (path === '/metrics/items') return json(route, ITEMS);
    return json(route, { code: 'not_found', message: `No stub for ${path}`, details: {}, fields: [] }, 404);
  });
}
