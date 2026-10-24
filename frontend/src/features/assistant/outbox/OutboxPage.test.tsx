import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { getListOutboxEmailsMockHandler } from '../../../api/generated/notifications/notifications.msw';
import type { OutboxEmailOut } from '../../../api/generated/model';
import { renderAtRoute } from '../../../test/router';
import { server } from '../../../test/server';
import { OutboxPage } from './OutboxPage';

function email(overrides: Partial<OutboxEmailOut> = {}): OutboxEmailOut {
  return {
    id: 1,
    to: ['compliance@clearpath.demo', 'dana.reviewer@clearpath.demo'],
    subject: 'CP-1042 findings summary',
    body: 'Two blocking findings on CP-1042.',
    html_body: '<p>Two blocking findings on <b>CP-1042</b>.</p>',
    item_id: 1042,
    thread_id: 't-1',
    sent_at: '2026-10-24T14:00:00Z',
    requested_by: { id: 3, name: 'Dana Reviewer' },
    approved_by: { id: 3, name: 'Dana Reviewer' },
    ...overrides,
  };
}

describe('OutboxPage', () => {
  it('says why it is empty and where emails come from', async () => {
    server.use(getListOutboxEmailsMockHandler([]));
    renderAtRoute(OutboxPage, { path: '/outbox' });
    expect(await screen.findByText('No emails yet')).toBeInTheDocument();
    expect(
      screen.getByText('Emails the assistant drafts land here after you approve them.'),
    ).toBeInTheDocument();
  });

  it('lists sent emails with recipients, item, requester and approver', async () => {
    server.use(
      getListOutboxEmailsMockHandler([
        email(),
        email({ id: 2, subject: 'Queue this week', item_id: null, to: ['legal@clearpath.demo'] }),
      ]),
    );
    renderAtRoute(OutboxPage, { path: '/outbox' });

    const table = await screen.findByRole('table', { name: 'Sent emails' });
    expect(within(table).getAllByRole('row')).toHaveLength(3); // header + two emails
    const [, first, second] = within(table).getAllByRole('row');
    if (first === undefined || second === undefined) throw new Error('expected two email rows');
    expect(
      within(first).getByText('compliance@clearpath.demo, dana.reviewer@clearpath.demo'),
    ).toBeInTheDocument();
    expect(within(first).getByRole('link', { name: 'CP-1042' })).toHaveAttribute('href', '/items/1042');
    expect(within(first).getAllByText('Dana Reviewer')).toHaveLength(2);
    expect(within(second).queryByRole('link')).toBeNull();
  });

  it('opens the HTML in a sandboxed iframe: no scripts, no same-origin', async () => {
    server.use(getListOutboxEmailsMockHandler([email()]));
    renderAtRoute(OutboxPage, { path: '/outbox' });

    await userEvent.click(await screen.findByRole('button', { name: 'CP-1042 findings summary' }));

    const detail = screen.getByRole('region', { name: 'CP-1042 findings summary' });
    const frame = within(detail).getByTitle('Email preview');
    expect(frame.tagName).toBe('IFRAME');
    expect(frame.getAttribute('sandbox')).toBe('');
    expect(frame.getAttribute('srcdoc')).toBe('<p>Two blocking findings on <b>CP-1042</b>.</p>');
    expect(within(detail).getByText('Approved by')).toBeInTheDocument();
  });

  it('falls back to the text body when there is no HTML part', async () => {
    server.use(getListOutboxEmailsMockHandler([email({ html_body: '' })]));
    renderAtRoute(OutboxPage, { path: '/outbox' });

    await userEvent.click(await screen.findByRole('button', { name: 'CP-1042 findings summary' }));

    const detail = screen.getByRole('region', { name: 'CP-1042 findings summary' });
    expect(within(detail).queryByTitle('Email preview')).toBeNull();
    expect(within(detail).getByText('Two blocking findings on CP-1042.')).toBeInTheDocument();
  });

  it('shows a one-line error with Retry when the list fails', async () => {
    server.use(
      http.get('*/api/outbox', () =>
        HttpResponse.json({ code: 'server_error', message: 'The outbox is unavailable.' }, { status: 500 }),
      ),
    );
    renderAtRoute(OutboxPage, { path: '/outbox' });
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('The outbox is unavailable.')).toBeInTheDocument();
    expect(within(alert).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
