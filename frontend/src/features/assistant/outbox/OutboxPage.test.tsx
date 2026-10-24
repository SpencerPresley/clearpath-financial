import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it } from 'vitest';

import { getGetMeMockHandler } from '../../../api/generated/me/me.msw';
import type { OutboxEmailOut } from '../../../api/generated/model';
import { getListOutboxEmailsMockHandler } from '../../../api/generated/notifications/notifications.msw';
import { renderApp } from '../../../test/renderApp';
import { server } from '../../../test/server';
import { assistantHandlers, threadFixture } from '../fixtures/handlers';
import { threadKey } from '../storage';

const VIEWER = { id: 3, name: 'Dana Reviewer' };

function email(overrides: Partial<OutboxEmailOut> = {}): OutboxEmailOut {
  return {
    id: 1,
    source: 'assistant',
    to: ['compliance@clearpath.demo', 'dana.reviewer@clearpath.demo'],
    subject: 'CP-1042 findings summary',
    body: 'Two blocking findings on CP-1042.',
    html_body: '<p>Two blocking findings on <b>CP-1042</b>.</p>',
    item_id: 1042,
    thread_id: 't-1',
    sent_at: '2026-10-24T14:00:00Z',
    requested_by: VIEWER,
    approved_by: VIEWER,
    ...overrides,
  };
}

function renderOutbox(emails: OutboxEmailOut[] | null, path = '/outbox') {
  server.use(
    getGetMeMockHandler({
      id: VIEWER.id,
      display_name: VIEWER.name,
      email: 'dana@clearpath.demo',
      roles: ['reviewer'],
      effective_roles: ['reviewer'],
      is_available: true,
    }),
    ...assistantHandlers({ runs: [], threads: [threadFixture({ id: 't-1', title: 'Email the findings' })] })
      .handlers,
  );
  if (emails !== null) server.use(getListOutboxEmailsMockHandler(emails));
  return renderApp(path);
}

afterEach(() => {
  window.localStorage.clear();
});

describe('OutboxPage', () => {
  it('says why it is empty, offers the assistant, and always says the mail is a demo', async () => {
    const user = userEvent.setup();
    renderOutbox([]);
    expect(await screen.findByText('No emails yet')).toBeInTheDocument();
    expect(
      screen.getByText('Emails the assistant drafts land here after you approve them.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Demo mail: nothing leaves ClearPath.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Open the assistant' }));
    expect(await screen.findByRole('complementary', { name: 'Assistant' })).toBeInTheDocument();
  });

  it('lists sent emails with recipients, item, requester and approver', async () => {
    renderOutbox([
      email({ requested_by: { id: 4, name: 'Sam Okafor' }, approved_by: { id: 5, name: 'Priya Raman' } }),
      email({ id: 2, subject: 'Queue this week', item_id: null, to: ['legal@clearpath.demo'] }),
    ]);

    const table = await screen.findByRole('table', { name: 'Sent emails' });
    expect(within(table).getAllByRole('row')).toHaveLength(3); // header + two emails
    const [, first, second] = within(table).getAllByRole('row');
    if (first === undefined || second === undefined) throw new Error('expected two email rows');
    expect(
      within(first).getByText('compliance@clearpath.demo, dana.reviewer@clearpath.demo'),
    ).toBeInTheDocument();
    expect(within(first).getByRole('link', { name: 'CP-1042' })).toHaveAttribute('href', '/items/1042');
    expect(within(first).getByText('Sam Okafor')).toBeInTheDocument();
    expect(within(first).getByText('Priya Raman')).toBeInTheDocument();
    expect(within(second).queryByRole('link')).toBeNull();
  });

  it('loads as the same table, header included, so nothing moves when rows arrive', async () => {
    server.use(
      http.get('*/api/outbox', async () => {
        await delay('infinite');
        return HttpResponse.json([]);
      }),
    );
    renderOutbox(null);
    const loading = await screen.findByRole('status', { name: 'Loading the outbox' });
    expect(loading.querySelector('thead th[data-col="subject"]')).toHaveTextContent('Subject');
    expect(loading.querySelector('table.app-outbox-table')).not.toBeNull();
  });

  it('opens the HTML in a sandboxed iframe (no scripts, no same-origin) and puts the email in the URL', async () => {
    const user = userEvent.setup();
    const { router } = renderOutbox([email()]);

    await user.click(await screen.findByRole('button', { name: 'CP-1042 findings summary' }));

    const detail = screen.getByRole('region', { name: 'CP-1042 findings summary' });
    const frame = within(detail).getByTitle('Email preview');
    expect(frame.tagName).toBe('IFRAME');
    expect(frame.getAttribute('sandbox')).toBe('');
    expect(frame.getAttribute('srcdoc')).toBe('<p>Two blocking findings on <b>CP-1042</b>.</p>');
    expect(within(detail).getByText('Approved by')).toBeInTheDocument();
    expect(within(detail).getByText('Approved and sent')).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ email: 1 });
  });

  it('opens the email named in ?email= (the assistant links here after a send)', async () => {
    renderOutbox([email(), email({ id: 7, subject: 'Re-reviews this week' })], '/outbox?email=7');
    expect(await screen.findByRole('region', { name: 'Re-reviews this week' })).toBeInTheDocument();
  });

  it('opens a row by clicking anywhere on it', async () => {
    const user = userEvent.setup();
    renderOutbox([email()]);
    const table = await screen.findByRole('table', { name: 'Sent emails' });
    const [, row] = within(table).getAllByRole('row');
    if (row === undefined) throw new Error('expected an email row');
    const requested = row.querySelector('td[data-col="requested"]');
    if (requested === null) throw new Error('expected a Requested by cell');
    await user.click(requested);
    expect(screen.getByRole('region', { name: 'CP-1042 findings summary' })).toBeInTheDocument();
  });

  it('falls back to the text body when there is no HTML part', async () => {
    const user = userEvent.setup();
    renderOutbox([email({ html_body: '' })]);

    await user.click(await screen.findByRole('button', { name: 'CP-1042 findings summary' }));

    const detail = screen.getByRole('region', { name: 'CP-1042 findings summary' });
    expect(within(detail).queryByTitle('Email preview')).toBeNull();
    expect(within(detail).getByText('Two blocking findings on CP-1042.')).toBeInTheDocument();
  });

  it('opens your thread behind an email in the assistant panel', async () => {
    const user = userEvent.setup();
    renderOutbox([email()], '/outbox?email=1');
    const detail = await screen.findByRole('region', { name: 'CP-1042 findings summary' });
    await user.click(within(detail).getByRole('button', { name: 'Open thread' }));

    const panel = await screen.findByRole('complementary', { name: 'Assistant' });
    expect(await within(panel).findByRole('heading', { name: 'Email the findings' })).toBeInTheDocument();
    expect(window.localStorage.getItem(threadKey(VIEWER.id))).toBe('t-1');
  });

  it("doesn't offer someone else's thread", async () => {
    renderOutbox([email({ requested_by: { id: 4, name: 'Sam Okafor' } })], '/outbox?email=1');
    const detail = await screen.findByRole('region', { name: 'CP-1042 findings summary' });
    expect(within(detail).queryByRole('button', { name: 'Open thread' })).toBeNull();
  });

  it('marks system mail (password resets, admins only) and shows its recipient, with no requester or approver', async () => {
    const user = userEvent.setup();
    renderOutbox([
      email({
        id: 9,
        source: 'system',
        subject: 'Reset your password',
        to: ['sam.okafor@clearpath.demo'],
        item_id: null,
        thread_id: '',
        requested_by: null,
        approved_by: null,
      }),
    ]);

    const table = await screen.findByRole('table', { name: 'Sent emails' });
    const [, row] = within(table).getAllByRole('row');
    if (row === undefined) throw new Error('expected an email row');
    expect(within(row).getByText('sam.okafor@clearpath.demo')).toBeInTheDocument();
    expect(within(row).getByText('System')).toBeInTheDocument();

    await user.click(within(row).getByRole('button', { name: 'Reset your password' }));
    const detail = screen.getByRole('region', { name: 'Reset your password' });
    expect(within(detail).getByText('Sent')).toBeInTheDocument();
    expect(within(detail).getByText('System mail, not drafted by the assistant')).toBeInTheDocument();
    expect(within(detail).getByText('sam.okafor@clearpath.demo')).toBeInTheDocument();
    expect(within(detail).queryByText('Approved by')).toBeNull();
    expect(within(detail).queryByRole('button', { name: 'Open thread' })).toBeNull();
  });

  it('shows a one-line error with Retry when the list fails', async () => {
    server.use(
      http.get('*/api/outbox', () =>
        HttpResponse.json({ code: 'server_error', message: 'The outbox is unavailable.' }, { status: 500 }),
      ),
    );
    renderOutbox(null);
    const line = await screen.findByText('The outbox is unavailable.');
    const alert = line.closest('[role="alert"]');
    if (!(alert instanceof HTMLElement)) throw new Error('expected the error inside an alert');
    expect(within(alert).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
