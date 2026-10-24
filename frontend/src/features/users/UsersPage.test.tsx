import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import type { UserCreateIn, UserOut, UserUpdateIn } from '../../api/generated/model';
import { ME_ADMIN, ME_LIBRARY_REVIEWER } from '../../test/fixtures/library';
import { TEAM } from '../../test/fixtures/users';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

let people: UserOut[] = [];
const patches: { id: number; body: UserUpdateIn }[] = [];
const creates: UserCreateIn[] = [];

beforeEach(() => {
  people = TEAM.map((u) => ({ ...u }));
  patches.length = 0;
  creates.length = 0;
  server.use(
    getGetMeMockHandler(ME_ADMIN),
    http.get('*/api/users', ({ request }) => {
      const all = new URL(request.url).searchParams.get('include_inactive') === 'true';
      return HttpResponse.json(all ? people : people.filter((u) => u.is_active));
    }),
    http.patch('*/api/admin/users/:id', async ({ params, request }) => {
      const id = Number(params.id);
      const body = (await request.json()) as UserUpdateIn;
      patches.push({ id, body });
      people = people.map((u) =>
        u.id === id
          ? {
              ...u,
              roles: body.roles ?? u.roles,
              is_active: body.is_active ?? u.is_active,
              is_available: body.is_available ?? u.is_available,
            }
          : u,
      );
      return HttpResponse.json(people.find((u) => u.id === id));
    }),
  );
});

const row = async (name: RegExp) => {
  const table = await screen.findByRole('table', { name: 'Users' });
  return within(table).getByRole('row', { name });
};

describe('Users', () => {
  it('is for admins only', async () => {
    server.use(getGetMeMockHandler(ME_LIBRARY_REVIEWER));
    renderApp('/users');
    expect(await screen.findByRole('heading', { name: 'Users are managed by admins' })).toBeInTheDocument();
  });

  it('lists everyone with roles, availability and whether they can sign in', async () => {
    renderApp('/users');

    const leah = await row(/Leah Brandt/);
    expect(within(leah).getByRole('button', { name: 'Reviewer' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(leah).getByRole('button', { name: 'Lead' })).toHaveAttribute('aria-pressed', 'false');
    expect(within(leah).getByRole('switch', { name: 'Leah Brandt available' })).not.toBeChecked();
    expect(within(leah).getByText('Out of office')).toBeInTheDocument();
    const priya = await row(/Priya Natarajan/);
    // Availability is about review work: a marketer has none to be out of.
    expect(within(priya).queryByRole('switch')).toBeNull();
    const old = await row(/Old Contractor/);
    expect(within(old).getByText('Deactivated')).toBeInTheDocument();
    expect(within(old).getByRole('button', { name: 'Reactivate Old Contractor' })).toBeInTheDocument();
  });

  it('changes roles, availability and active, one request each', async () => {
    renderApp('/users');

    const dana = await row(/Dana Kim/);
    await userEvent.click(within(dana).getByRole('button', { name: 'Lead' }));
    await waitFor(() => {
      expect(patches).toContainEqual({ id: 2, body: { roles: ['reviewer', 'lead'] } });
    });
    await userEvent.click(
      within(await row(/Leah Brandt/)).getByRole('switch', { name: 'Leah Brandt available' }),
    );
    await waitFor(() => {
      expect(patches).toContainEqual({ id: 3, body: { is_available: true } });
    });
    await userEvent.click(
      within(await row(/Nikhil Rao/)).getByRole('button', { name: 'Deactivate Nikhil Rao' }),
    );
    await waitFor(() => {
      expect(patches).toContainEqual({ id: 4, body: { is_active: false } });
    });
    expect(within(await row(/Nikhil Rao/)).getByText('Deactivated')).toBeInTheDocument();
  });

  it("can't deactivate yourself, and shows why the server refused a role change", async () => {
    server.use(
      http.patch('*/api/admin/users/1', () =>
        HttpResponse.json(
          {
            code: 'conflict',
            message: 'Morgan Admin is the only admin. Make someone else an admin first.',
            details: {},
            fields: [],
          },
          { status: 409 },
        ),
      ),
    );
    people = people.map((u) => (u.id === 1 ? { ...u, roles: ['lead', 'admin'] } : u));
    renderApp('/users');

    const me = await row(/Morgan Admin/);
    expect(within(me).getByRole('button', { name: 'Deactivate Morgan Admin' })).toBeDisabled();
    expect(within(me).getByText('You')).toBeInTheDocument();
    await userEvent.click(within(me).getByRole('button', { name: 'Admin' }));
    // Not findByRole('alert') alone: the topbar's API-health badge is an alert too when the mock says it's down.
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.map((a) => a.textContent)).toContain(
      "Couldn't change Morgan Admin: Morgan Admin is the only admin. Make someone else an admin first.",
    );
    expect(within(await row(/Morgan Admin/)).getByRole('button', { name: 'Admin' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('adds a user, and puts a refused email on its field', async () => {
    let attempts = 0;
    server.use(
      http.post('*/api/admin/users', async ({ request }) => {
        const body = (await request.json()) as UserCreateIn;
        creates.push(body);
        attempts += 1;
        if (attempts === 1) {
          return HttpResponse.json(
            {
              code: 'invalid_input',
              message: 'Someone already has this email.',
              details: {},
              fields: [
                { loc: ['body', 'email'], message: 'Someone already has this email.', type: 'invalid' },
              ],
            },
            { status: 422 },
          );
        }
        const created: UserOut = {
          id: 9,
          email: body.email,
          display_name: body.display_name,
          roles: body.roles,
          is_available: true,
          is_active: true,
        };
        people = [...people, created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    renderApp('/users');

    await userEvent.click(await screen.findByRole('button', { name: 'Add user' }));
    const form = screen.getByRole('form', { name: 'New user' });
    await userEvent.type(within(form).getByRole('textbox', { name: 'Name' }), 'Jo Park');
    await userEvent.type(within(form).getByRole('textbox', { name: 'Email' }), 'dana@clearpath.demo');
    await userEvent.click(within(form).getByRole('checkbox', { name: 'Reviewer' }));
    await userEvent.type(within(form).getByLabelText('Temporary password'), 'plum-lantern-orbit-42');
    await userEvent.click(within(form).getByRole('button', { name: 'Add user' }));

    expect(await within(form).findByText('Someone already has this email.')).toBeInTheDocument();
    const email = within(form).getByRole('textbox', { name: 'Email' });
    await userEvent.clear(email);
    await userEvent.type(email, 'jo.park@clearpath.demo');
    await userEvent.click(within(form).getByRole('button', { name: 'Add user' }));

    expect(await row(/Jo Park/)).toBeInTheDocument();
    expect(creates[1]).toEqual({
      email: 'jo.park@clearpath.demo',
      display_name: 'Jo Park',
      roles: ['reviewer'],
      password: 'plum-lantern-orbit-42',
    });
    expect(screen.queryByRole('form', { name: 'New user' })).toBeNull();
  });
});
