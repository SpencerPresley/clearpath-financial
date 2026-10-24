/*
 * The notifications API for e2e and UI-review screenshots, layered over stubApi (Playwright tries the most
 * recently added route first). The viewer is Priya Natarajan, CP-1042's owner, so the review fixture's item is
 * hers and no notification names her as the actor. `deliver` adds a row the next poll picks up.
 */
import type { Page, Route } from '@playwright/test';

import type { CommentOut, NotificationOut, NotificationPageOut } from '../src/api/generated/model';
import { SAM } from '../src/test/fixtures/notifications';
import { COMMENTS, MARKETER } from '../src/test/fixtures/review';

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

/** The comment MENTION_ON_1042 points at: Sam asks Priya on v2. */
export const MENTION_COMMENT: CommentOut = {
  id: 311,
  version_n: 2,
  author: SAM,
  body: '@Priya Natarajan can you confirm the APR range in the footer matches the current offer terms?',
  span: null,
  mentions: [MARKETER],
  created_at: '2026-10-24T13:05:00Z',
};

export interface NotificationsStub {
  posted: string[];
  deliver: (row: NotificationOut) => void;
}

export type InboxMode = 'data' | 'loading' | 'error';

export async function stubNotifications(
  page: Page,
  rows: NotificationOut[],
  mode: InboxMode = 'data',
): Promise<NotificationsStub> {
  let inbox = structuredClone(rows);
  const posted: string[] = [];
  const view = (): NotificationPageOut => ({
    rows: inbox,
    unread_count: inbox.filter((row) => row.read_at === null).length,
  });

  await page.route('**/api/me', (route) =>
    json(route, {
      id: MARKETER.id,
      display_name: MARKETER.name,
      email: 'priya@clearpath.demo',
      roles: ['marketer', 'reviewer'],
      effective_roles: ['marketer', 'reviewer'],
      is_available: true,
    }),
  );
  await page.route('**/api/items/1042/comments*', (route) => json(route, [...COMMENTS, MENTION_COMMENT]));
  await page.route('**/api/notifications**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api/, '');
    if (request.method() === 'GET' && path === '/notifications') {
      if (mode === 'loading') return new Promise<never>(() => undefined);
      if (mode === 'error') {
        return json(route, { code: 'server_error', message: 'Notifications are temporarily unavailable.' }, 503);
      }
      return json(route, view());
    }
    const now = new Date().toISOString();
    if (path === '/notifications/read-all') {
      posted.push('read-all');
      const marked = view().unread_count;
      inbox = inbox.map((row) => ({ ...row, read_at: row.read_at ?? now }));
      return json(route, { marked });
    }
    const m = /^\/notifications\/(\d+)\/read$/.exec(path);
    if (m) {
      const id = Number(m[1]);
      posted.push(`read ${String(id)}`);
      inbox = inbox.map((row) => (row.id === id ? { ...row, read_at: row.read_at ?? now } : row));
      return route.fulfill({ status: 204 });
    }
    return json(route, { code: 'not_found', message: `No stub for ${path}` }, 404);
  });

  return {
    posted,
    deliver: (row) => {
      inbox = [row, ...inbox];
    },
  };
}
