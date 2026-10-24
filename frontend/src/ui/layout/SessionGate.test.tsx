import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import type { MeOut } from '../../api/generated/model';
import { server } from '../../test/server';
import { renderWithQuery } from '../../test/render';
import { SessionGate } from './SessionGate';
import { useViewer } from './Viewer';

const ME: MeOut = {
  id: 4,
  display_name: 'Priya Raman',
  email: 'lead@clearpath.demo',
  roles: ['lead'],
  effective_roles: ['lead', 'reviewer'],
  is_available: true,
};

function Who() {
  const viewer = useViewer();
  return <p>{`${viewer.name}: ${viewer.roles.join(',')}`}</p>;
}

describe('SessionGate', () => {
  it('provides the signed-in viewer with effective roles', async () => {
    server.use(http.get('*/api/me', () => HttpResponse.json(ME)));
    renderWithQuery(
      <SessionGate>
        <Who />
      </SessionGate>,
    );
    expect(await screen.findByText('Priya Raman: lead,reviewer')).toBeInTheDocument();
  });

  it('shows sign-in when there is no session, then the app after signing in', async () => {
    let session = false;
    const logins: unknown[] = [];
    server.use(
      http.get('*/api/me', () =>
        session
          ? HttpResponse.json(ME)
          : HttpResponse.json({ code: 'not_authenticated', message: 'Sign in.' }, { status: 401 }),
      ),
      http.get('*/_allauth/browser/v1/auth/session', () =>
        HttpResponse.json({ status: 401 }, { status: 401 }),
      ),
      http.post('*/_allauth/browser/v1/auth/login', async ({ request }) => {
        logins.push(await request.json());
        session = true;
        return HttpResponse.json({ status: 200, data: {} });
      }),
    );
    renderWithQuery(
      <SessionGate>
        <Who />
      </SessionGate>,
    );
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /lead@clearpath\.demo/ }));
    expect(screen.getByRole('textbox', { name: 'Email' })).toHaveValue('lead@clearpath.demo');
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse battery');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Priya Raman: lead,reviewer')).toBeInTheDocument();
    expect(logins).toEqual([{ email: 'lead@clearpath.demo', password: 'correct horse battery' }]);
  });

  it("shows allauth's message when the password is wrong", async () => {
    server.use(
      http.get('*/api/me', () =>
        HttpResponse.json({ code: 'not_authenticated', message: 'x' }, { status: 401 }),
      ),
      http.get('*/_allauth/browser/v1/auth/session', () =>
        HttpResponse.json({ status: 401 }, { status: 401 }),
      ),
      http.post('*/_allauth/browser/v1/auth/login', () =>
        HttpResponse.json(
          {
            status: 400,
            errors: [
              { message: 'The email address and/or password you specified are not correct.', code: 'x' },
            ],
          },
          { status: 400 },
        ),
      ),
    );
    renderWithQuery(
      <SessionGate>
        <Who />
      </SessionGate>,
    );
    await userEvent.type(await screen.findByRole('textbox', { name: 'Email' }), 'reviewer@clearpath.demo');
    await userEvent.type(screen.getByLabelText('Password'), 'nope-nope-nope');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(
      await screen.findByText('The email address and/or password you specified are not correct.'),
    ).toBeInTheDocument();
  });

  it('says the account could not load on a server error, with retry', { timeout: 10_000 }, async () => {
    server.use(
      http.get('*/api/me', () =>
        HttpResponse.json({ code: 'x', message: 'Database is down.' }, { status: 500 }),
      ),
    );
    renderWithQuery(
      <SessionGate>
        <Who />
      </SessionGate>,
    );
    // Two retries with backoff (1s + 2s) before the error shows.
    expect(await screen.findByText('Database is down.', {}, { timeout: 6000 })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
