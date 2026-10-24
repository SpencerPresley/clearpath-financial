import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import { getImportsMock } from '../../api/generated/imports/imports.msw';
import { getLibraryMock } from '../../api/generated/library/library.msw';
import type { DemoResetOut } from '../../api/generated/model';
import { getPartnersMock } from '../../api/generated/partners/partners.msw';
import { getUsersMock } from '../../api/generated/users/users.msw';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';
import { renderWithQuery } from '../../test/render';
import { ResetDemoDialog } from './ResetDemo';

function job(status: DemoResetOut['status'], extra: Partial<DemoResetOut> = {}): DemoResetOut {
  return {
    id: 7,
    status,
    requested_at: '2026-10-24T22:00:00Z',
    started_at: null,
    finished_at: null,
    seeded_items: 0,
    error: '',
    ...extra,
  };
}

describe('ResetDemoDialog', () => {
  it('starts a reset, polls it, and closes when it is done', async () => {
    const user = userEvent.setup();
    let polls = 0;
    let closed = false;
    server.use(
      http.post('*/api/admin/demo/reset', () => HttpResponse.json(job('queued'), { status: 202 })),
      http.get('*/api/admin/demo/resets/7', () => {
        polls += 1;
        return HttpResponse.json(polls < 2 ? job('running') : job('done', { seeded_items: 42 }));
      }),
    );
    renderWithQuery(
      <ResetDemoDialog
        isOpen
        onOpenChange={(open) => {
          closed = !open;
        }}
      />,
    );

    expect(screen.getByRole('alertdialog', { name: 'Reset the demo?' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Reset demo' }));

    expect(await screen.findByRole('button', { name: 'Resetting…' })).toBeDisabled();
    await waitFor(
      () => {
        expect(closed).toBe(true);
      },
      { timeout: 4000 },
    );
    expect(polls).toBeGreaterThanOrEqual(2);
  });

  it('can be closed while the reset runs, and keeps watching it', async () => {
    const user = userEvent.setup();
    let polls = 0;
    const changes: boolean[] = [];
    server.use(
      http.post('*/api/admin/demo/reset', () => HttpResponse.json(job('queued'), { status: 202 })),
      http.get('*/api/admin/demo/resets/7', () => {
        polls += 1;
        return HttpResponse.json(polls < 3 ? job('queued') : job('done', { seeded_items: 42 }));
      }),
    );
    renderWithQuery(
      <ResetDemoDialog
        isOpen
        onOpenChange={(open) => {
          changes.push(open);
        }}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Reset demo' }));
    const close = await screen.findByRole('button', { name: 'Run in background' });
    expect(close).toBeEnabled();
    await user.click(close);
    expect(changes).toEqual([false]);

    await waitFor(
      () => {
        expect(polls).toBeGreaterThanOrEqual(3);
      },
      { timeout: 5000 },
    );
  });

  it('shows why a reset failed and lets the admin try again', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('*/api/admin/demo/reset', () => HttpResponse.json(job('queued'), { status: 202 })),
      http.get('*/api/admin/demo/resets/7', () =>
        HttpResponse.json(job('failed', { error: 'The reset failed and nothing changed.' })),
      ),
    );
    renderWithQuery(<ResetDemoDialog isOpen onOpenChange={() => undefined} />);

    await user.click(screen.getByRole('button', { name: 'Reset demo' }));

    expect(await screen.findByRole('alert', {}, { timeout: 3000 })).toHaveTextContent(
      'The reset failed and nothing changed.',
    );
    expect(screen.getByRole('button', { name: 'Reset demo' })).toBeEnabled();
  });
});

describe('Reset demo from the account menu', () => {
  it('leaves the deleted import job for the landing page and drops the old cache', async () => {
    const user = userEvent.setup();
    server.use(
      ...getLibraryMock(),
      ...getImportsMock(),
      ...getPartnersMock(),
      ...getUsersMock(),
      getGetMeMockHandler({
        id: 9,
        display_name: 'Avery Kim',
        email: 'admin@clearpath.demo',
        roles: ['admin'],
        effective_roles: ['admin'],
        is_available: true,
      }),
      http.post('*/api/admin/demo/reset', () => HttpResponse.json(job('queued'), { status: 202 })),
      http.get('*/api/admin/demo/resets/7', () => HttpResponse.json(job('done', { seeded_items: 44 }))),
    );
    // The review's repro: the Import page open on job 2, which the reset deletes.
    const { router, queryClient } = renderApp('/import?job=2');
    await waitFor(() => {
      expect(queryClient.getQueryData(['/api/imports/2'])).toBeDefined();
    });
    await user.click(screen.getByRole('button', { name: /account$/ }));
    await user.click(await screen.findByRole('button', { name: 'Reset demo…' }));
    const dialog = await screen.findByRole('alertdialog', { name: 'Reset the demo?' });
    await user.click(within(dialog).getByRole('button', { name: 'Reset demo' }));

    await waitFor(
      () => {
        expect(router.state.location.pathname).toBe('/import');
        expect(router.state.location.search).toEqual({});
        expect(queryClient.getQueryData(['/api/imports/2'])).toBeUndefined();
      },
      { timeout: 4000 },
    );
    // The start screen, not the deleted job's preview.
    expect(await screen.findByRole('region', { name: 'Start an import' })).toBeInTheDocument();
    // Same person, same session: the shell stays up (no sign-in, no blank loading screen).
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
  });
});
