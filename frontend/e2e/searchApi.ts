/*
 * `GET /items?q=` for the quick-jump box, layered over stubApi (Playwright tries the most recently added route
 * first; stubApi's own `/items` ignores `q`). `mode` holds the request open or fails it for the state shots.
 */
import type { Page } from '@playwright/test';

import { jumpResults } from '../src/test/fixtures/search';

export type SearchMode = 'data' | 'loading' | 'error';

export async function stubSearch(page: Page, mode: SearchMode = 'data'): Promise<{ asked: string[] }> {
  const asked: string[] = [];
  await page.route(
    (url) => url.pathname === '/api/items' && url.searchParams.has('q'),
    async (route) => {
      const q = new URL(route.request().url()).searchParams.get('q') ?? '';
      asked.push(q);
      if (mode === 'loading') return new Promise<never>(() => undefined);
      if (mode === 'error') {
        return route.fulfill({
          status: 503,
          json: { code: 'server_error', message: 'Search is temporarily unavailable.' },
        });
      }
      const rows = jumpResults(q);
      return route.fulfill({ json: { rows, next_cursor: null, total: rows.length } });
    },
  );
  return { asked };
}
