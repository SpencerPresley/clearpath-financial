/*
 * Browser-mode tests run without MSW (no service worker in the test page), so this stubs window.fetch with the
 * queue fixtures. Unknown API paths answer 404 with an ErrorOut body, so a missing stub fails loudly.
 */
import { vi } from 'vitest';

import type { ItemRowOut, MeOut } from '../api/generated/model';
import {
  FINDINGS,
  makeDetail,
  ME_REVIEWER,
  PARTNERS,
  queueRows,
  STATS,
  USERS,
} from '../features/queue/fixtures';

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

export function stubApi({ me = ME_REVIEWER, rows = queueRows() }: { me?: MeOut; rows?: ItemRowOut[] } = {}) {
  const realFetch = window.fetch.bind(window);
  return vi.spyOn(window, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(input instanceof Request ? input.url : String(input), window.location.origin);
    const path = url.pathname;
    if (!path.startsWith('/api/') && !path.startsWith('/_allauth/')) return realFetch(input, init);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (path === '/api/me') return Promise.resolve(json(me));
    if (path === '/api/health') return Promise.resolve(json({ status: 'ok', database: true }));
    if (path === '/api/items/stats') return Promise.resolve(json(STATS));
    if (path === '/api/items') return Promise.resolve(json({ rows, next_cursor: null }));
    if (path === '/api/views') return Promise.resolve(json([]));
    if (path === '/api/users') return Promise.resolve(json(USERS));
    if (path === '/api/partners') return Promise.resolve(json(PARTNERS));
    const findings = /^\/api\/items\/(\d+)\/findings$/.exec(path);
    if (findings) return Promise.resolve(json(FINDINGS));
    const item = /^\/api\/items\/(\d+)$/.exec(path);
    if (item) {
      const row = rows.find((r) => String(r.id) === item[1]);
      if (row === undefined) return Promise.resolve(json({ code: 'not_found', message: 'Not found.' }, 404));
      return Promise.resolve(method === 'PATCH' ? json(row) : json(makeDetail(row)));
    }
    return Promise.resolve(json({ code: 'not_found', message: `No stub for ${method} ${path}` }, 404));
  });
}
