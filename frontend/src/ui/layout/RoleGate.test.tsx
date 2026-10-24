import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';
import type { Role } from '../domain';

function as(roles: Role[]) {
  const requests: string[] = [];
  server.use(
    getGetMeMockHandler({
      id: 7,
      display_name: 'Test Person',
      email: 'test@clearpath.test',
      roles,
      effective_roles: roles,
      is_available: true,
    }),
    // Anything the gated page would ask for: the gate must not let it mount.
    http.get('*/api/items*', ({ request }) => {
      requests.push(request.url);
      return HttpResponse.json({ code: 'permission_denied', message: 'No.' }, { status: 403 });
    }),
  );
  return requests;
}

describe('pages a role cannot use say so at once', () => {
  it.each<[string, Role[], string, string]>([
    ['/queue', ['marketer'], 'The queue is for reviewers and leads', 'My submissions'],
    ['/queue?view=mine', ['admin'], 'The queue is for reviewers and leads', 'Import'],
    ['/mine', ['reviewer'], 'My submissions is for marketers', 'Queue'],
    ['/mine/12/resubmit', ['lead', 'reviewer'], 'Resubmitting is for marketers', 'Queue'],
    ['/submit', ['admin'], 'New submission is for marketers', 'Import'],
    ['/metrics', ['marketer'], 'Metrics is for reviewers, leads and admins', 'My submissions'],
  ])('%s for %j', async (path, roles, refusal, landing) => {
    const requests = as(roles);
    renderApp(path);

    expect(await screen.findByRole('heading', { name: refusal })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: `Open ${landing}` })).toBeInTheDocument();
    expect(screen.queryByRole('status', { busy: true })).toBeNull();
    expect(requests).toEqual([]);
  });
});
