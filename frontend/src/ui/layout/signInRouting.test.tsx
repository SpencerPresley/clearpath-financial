/*
 * Walkthrough-1 S1: switching people in one tab. Sign-in lands on the signed-in person's own screen unless they
 * followed a link to a screen they can open; sign-out drops the previous person's cache and URL.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it } from 'vitest';

import { getItemsMock } from '../../api/generated/items/items.msw';
import { getLibraryMock } from '../../api/generated/library/library.msw';
import type { MeOut } from '../../api/generated/model';
import { getPartnersMock } from '../../api/generated/partners/partners.msw';
import { getUsersMock } from '../../api/generated/users/users.msw';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

const PEOPLE: Record<string, MeOut> = {
  'reviewer@clearpath.demo': {
    id: 1,
    email: 'reviewer@clearpath.demo',
    display_name: 'Dana Reyes',
    roles: ['reviewer'],
    effective_roles: ['reviewer'],
    is_available: true,
  },
  'sam@clearpath.demo': {
    id: 2,
    email: 'sam@clearpath.demo',
    display_name: 'Samuel Ortega',
    roles: ['reviewer'],
    effective_roles: ['reviewer'],
    is_available: true,
  },
  'marketer@clearpath.demo': {
    id: 3,
    email: 'marketer@clearpath.demo',
    display_name: 'Priya Raman',
    roles: ['marketer'],
    effective_roles: ['marketer'],
    is_available: true,
  },
};

/** A fake allauth + /api/me: `session` is whoever signed in last, or null. */
function backend(initial: string | null) {
  const state = { session: initial };
  server.use(
    ...getItemsMock(),
    ...getUsersMock(),
    ...getPartnersMock(),
    ...getLibraryMock(),
    http.get('*/api/me', () => {
      const me = state.session === null ? undefined : PEOPLE[state.session];
      return me === undefined
        ? HttpResponse.json({ code: 'not_authenticated', message: 'Sign in.' }, { status: 401 })
        : HttpResponse.json(me);
    }),
    http.get('*/_allauth/browser/v1/auth/session', () => HttpResponse.json({ status: 401 }, { status: 401 })),
    http.post('*/_allauth/browser/v1/auth/login', async ({ request }) => {
      const { email } = (await request.json()) as { email: string };
      state.session = email;
      return HttpResponse.json({ status: 200, data: {} });
    }),
    http.delete('*/_allauth/browser/v1/auth/session', () => {
      state.session = null;
      return HttpResponse.json({ status: 401 }, { status: 401 });
    }),
  );
  return state;
}

async function signInAs(email: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByRole('textbox', { name: 'Email' }), email);
  await user.type(screen.getByLabelText('Password'), 'pw');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
}

async function signOut() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: /account$/ }));
  await user.click(await screen.findByRole('button', { name: 'Sign out' }));
  await screen.findByRole('heading', { name: 'Sign in' });
}

afterEach(() => {
  window.localStorage.clear();
});

describe('sign-in routing', () => {
  it("sends the next person to their own landing after a sign-out, not the last person's screen", async () => {
    backend('reviewer@clearpath.demo');
    const { router, queryClient } = renderApp('/queue?view=mine');
    expect(await screen.findByRole('heading', { name: 'Queue', level: 1 })).toBeInTheDocument();
    await waitFor(() => {
      expect(window.sessionStorage.getItem('clearpath.queueTrail')).not.toBeNull();
    });

    await signOut();
    // Only the (signed-out) session query is left: nothing of Dana's is cached for the next person.
    await waitFor(() => {
      expect(router.state.location.href).toBe('/');
      expect(
        queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.queryKey[0]),
      ).toEqual(['/api/me']);
    });
    // Nor Dana's queue order in this tab: "Next item" would walk her view.
    expect(window.sessionStorage.getItem('clearpath.queueTrail')).toBeNull();

    await signInAs('marketer@clearpath.demo');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/mine');
    });
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    expect(within(nav).getByRole('link', { name: 'My submissions' })).toHaveAttribute('aria-current', 'page');
  });

  it('keeps a followed link the person can open', async () => {
    backend(null);
    const { router } = renderApp('/library');

    await signInAs('marketer@clearpath.demo');
    expect(await screen.findByRole('heading', { name: 'Library', level: 1 })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/library');
  });

  it("replaces a followed link the person can't open with their landing", async () => {
    backend(null);
    const { router } = renderApp('/queue');

    await signInAs('marketer@clearpath.demo');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/mine');
    });
  });

  it('after a session expires, a different person starts at their landing; the same person stays put', async () => {
    const state = backend('reviewer@clearpath.demo');
    const { router, queryClient } = renderApp('/library');
    expect(await screen.findByRole('heading', { name: 'Library', level: 1 })).toBeInTheDocument();

    state.session = null; // expired server-side
    await queryClient.refetchQueries({ queryKey: ['/api/me'] });
    await signInAs('sam@clearpath.demo');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/queue');
    });

    await router.navigate({ to: '/library' });
    state.session = null;
    await queryClient.refetchQueries({ queryKey: ['/api/me'] });
    await signInAs('sam@clearpath.demo');
    expect(await screen.findByRole('heading', { name: 'Library', level: 1 })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/library');
  });
});
