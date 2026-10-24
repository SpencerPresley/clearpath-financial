/*
 * API stand-in for the Users screen and the account menu's availability switch (walkthrough S16), for e2e and
 * the UI-review screenshots. Serves src/test/fixtures/users.ts and applies PATCH/POST to its own copy, so a flow
 * runs end to end; 409 for removing the last admin or deactivating yourself, as the server does.
 */
import type { Page, Route } from '@playwright/test';

import type { MeOut, UserCreateIn, UserOut, UserUpdateIn } from '../src/api/generated/model';
import { ME_ADMIN } from '../src/test/fixtures/library';
import { TEAM, WORKLOAD } from '../src/test/fixtures/users';

export interface UsersStubState {
  posted: { method: string; path: string; body: unknown }[];
  people: UserOut[];
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

export async function stubUsersApi(page: Page, options: { me?: MeOut } = {}): Promise<UsersStubState> {
  const state: UsersStubState = { posted: [], people: TEAM.map((u) => ({ ...u })) };
  let me: MeOut = { ...(options.me ?? ME_ADMIN) };

  await page.route(/\/(api|_allauth)\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, '');
    const method = request.method();
    const body: unknown = method === 'GET' ? undefined : request.postDataJSON();
    if (method !== 'GET') state.posted.push({ method, path, body });

    if (path === '/health') return json(route, { status: 'ok', database: true });
    if (path === '/me' && method === 'GET') return json(route, me);
    if (path === '/me' && method === 'PATCH') {
      me = { ...me, is_available: (body as { is_available?: boolean }).is_available ?? me.is_available };
      return json(route, me);
    }
    if (path === '/users/workload') return json(route, WORKLOAD);
    if (path === '/users') {
      const all = url.searchParams.get('include_inactive') === 'true';
      return json(route, all ? state.people : state.people.filter((u) => u.is_active));
    }
    if (path === '/admin/users' && method === 'POST') {
      const data = body as UserCreateIn;
      const created: UserOut = {
        id: 100 + state.people.length,
        email: data.email,
        display_name: data.display_name,
        roles: data.roles,
        is_available: true,
        is_active: true,
      };
      state.people = [...state.people, created];
      return json(route, created, 201);
    }
    const m = /^\/admin\/users\/(\d+)$/.exec(path);
    if (m && method === 'PATCH') {
      const id = Number(m[1]);
      const data = body as UserUpdateIn;
      const target = state.people.find((u) => u.id === id);
      if (target === undefined)
        return json(route, { code: 'not_found', message: `User ${String(id)} doesn't exist.` }, 404);
      const admins = state.people.filter((u) => u.is_active && u.roles.includes('admin'));
      const losesAdmin =
        target.roles.includes('admin') &&
        (data.is_active === false ||
          (data.roles !== undefined && data.roles !== null && !data.roles.includes('admin')));
      if (data.is_active === false && id === me.id) {
        return json(
          route,
          { code: 'conflict', message: "You can't deactivate your own account. Ask another admin." },
          409,
        );
      }
      if (losesAdmin && admins.length === 1) {
        return json(
          route,
          {
            code: 'conflict',
            message: `${target.display_name} is the only admin. Make someone else an admin first.`,
          },
          409,
        );
      }
      const next: UserOut = {
        ...target,
        roles: data.roles ?? target.roles,
        is_active: data.is_active ?? target.is_active,
        is_available: data.is_available ?? target.is_available,
      };
      state.people = state.people.map((u) => (u.id === id ? next : u));
      return json(route, next);
    }
    if (path.startsWith('/notifications')) return json(route, { rows: [], unread: 0, next_cursor: null });
    return json(route, { code: 'not_found', message: `No stub for ${method} ${path}` }, 404);
  });
  return state;
}
