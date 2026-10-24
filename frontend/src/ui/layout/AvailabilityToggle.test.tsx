import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import type { MeOut, MeUpdateIn } from '../../api/generated/model';
import { ME_ADMIN, ME_LIBRARY_REVIEWER } from '../../test/fixtures/library';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

async function openAccount(name: string) {
  await userEvent.click(await screen.findByRole('button', { name: `${name}, account` }));
  return screen.findByRole('dialog', { name: 'Account' });
}

describe('Availability in the account menu', () => {
  it('lets a reviewer mark themselves out of office, and back', async () => {
    let me: MeOut = { ...ME_LIBRARY_REVIEWER };
    const sent: MeUpdateIn[] = [];
    server.use(
      http.get('*/api/me', () => HttpResponse.json(me)),
      http.patch('*/api/me', async ({ request }) => {
        const body = (await request.json()) as MeUpdateIn;
        sent.push(body);
        me = { ...me, is_available: body.is_available ?? me.is_available };
        return HttpResponse.json(me);
      }),
    );
    renderApp('/library');

    const panel = await openAccount('Dana Reyes');
    const toggle = within(panel).getByRole('switch', { name: 'Available for new reviews' });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);

    await waitFor(() => {
      expect(sent).toEqual([{ is_available: false }]);
    });
    expect(await within(panel).findByText('Out of office')).toBeInTheDocument();
    expect(within(panel).getByRole('switch', { name: 'Available for new reviews' })).not.toBeChecked();
  });

  it("isn't offered to someone with no review work", async () => {
    server.use(getGetMeMockHandler(ME_ADMIN));
    renderApp('/library');

    const panel = await openAccount('Morgan Admin');
    expect(within(panel).queryByRole('switch')).toBeNull();
  });
});
