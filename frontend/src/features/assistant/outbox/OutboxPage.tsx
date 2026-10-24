/*
 * Outbox (decisions.md "Assistant"): the demo's stand-in for real mail. Rows are emails the assistant drafted
 * and a person approved, plus, for admins only, the app's own mail (`source: 'system'`, e.g. password resets),
 * which has a recipient but no requester, approver or thread, and whose body the server never stores (it can
 * hold a sign-in link). The HTML part is rendered only inside a sandboxed iframe: `sandbox=""` turns off
 * scripts, forms, popups and same-origin access, so the message can't reach the app or the session.
 *
 * The open email is in the URL (`?email=<id>`), so the assistant's "Open in Outbox" lands on it. Columns are
 * sized in CSS and a container query on .app-outbox drops To and Requested by when the page is narrow (beside
 * the assistant panel); with an email open, the list keeps Sent, Subject and Item and the pane has the rest.
 */
import { Link } from '@tanstack/react-router';
import type { MouseEvent } from 'react';
import { z } from 'zod';

import type { OutboxEmailOut } from '../../../api/generated/model';
import { useListOutboxEmails } from '../../../api/generated/notifications/notifications';
import { Button } from '../../../ui/Button';
import { EmptyState } from '../../../ui/EmptyState';
import { apiErrorMessage } from '../../../ui/forms/apiErrors';
import { IconButton } from '../../../ui/IconButton';
import { useViewer } from '../../../ui/layout/Viewer';
import { RelativeAge } from '../../../ui/RelativeAge';
import { openAssistant, openAssistantThread } from '../storage';

export const outboxSearchSchema = z.object({
  email: z.coerce.number().int().positive().optional().catch(undefined),
});
export type OutboxSearch = z.infer<typeof outboxSearchSchema>;

const COLUMNS = [
  { id: 'sent', label: 'Sent' },
  { id: 'to', label: 'To' },
  { id: 'subject', label: 'Subject' },
  { id: 'item', label: 'Item' },
  { id: 'requested', label: 'Requested by' },
  { id: 'approved', label: 'Approved by' },
] as const;
type ColumnId = (typeof COLUMNS)[number]['id'];
/** With an email open, the pane shows To and the people. */
const COMPACT: ReadonlySet<ColumnId> = new Set(['sent', 'subject', 'item']);

const sentFormat = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' });

function itemKey(id: number): string {
  return `CP-${String(id)}`;
}

function ItemLink({ id }: { id: number | null }) {
  if (id === null) return <span className="app-muted">—</span>;
  return (
    <Link to="/items/$itemId" params={{ itemId: String(id) }} className="app-outbox-item">
      {itemKey(id)}
    </Link>
  );
}

function Head({ columns }: { columns: readonly (typeof COLUMNS)[number][] }) {
  return (
    <thead>
      <tr className="app-outbox-head">
        {columns.map((column) => (
          <th key={column.id} scope="col" data-col={column.id}>
            {column.label}
          </th>
        ))}
      </tr>
    </thead>
  );
}

function OutboxRow({
  email,
  columns,
  selected,
  onSelect,
  now,
}: {
  email: OutboxEmailOut;
  columns: readonly (typeof COLUMNS)[number][];
  selected: boolean;
  onSelect: () => void;
  now: Date;
}) {
  const to = email.to.join(', ');
  const cell = (id: ColumnId) => {
    switch (id) {
      case 'sent':
        return <RelativeAge at={email.sent_at} now={now} />;
      case 'to':
        return to;
      case 'subject':
        return (
          <button type="button" className="app-outbox-subject" aria-pressed={selected} onClick={onSelect}>
            {email.subject}
          </button>
        );
      case 'item':
        return <ItemLink id={email.item_id} />;
      case 'requested':
        return email.requested_by?.name ?? <span className="app-muted">System</span>;
      case 'approved':
        return email.approved_by?.name ?? <span className="app-muted">—</span>;
    }
  };
  // The whole row opens the email for the mouse; the Subject button stays the keyboard target.
  const onRowClick = (event: MouseEvent<HTMLTableRowElement>) => {
    if ((event.target as HTMLElement).closest('a, button') === null) onSelect();
  };
  return (
    <tr className="app-outbox-row" data-selected={selected ? 'true' : undefined} onClick={onRowClick}>
      {columns.map((column) => (
        <td key={column.id} data-col={column.id} title={column.id === 'to' ? to : undefined}>
          {cell(column.id)}
        </td>
      ))}
    </tr>
  );
}

function OutboxDetail({ email, onClose }: { email: OutboxEmailOut; onClose: () => void }) {
  const viewer = useViewer();
  const headingId = `outbox-email-${String(email.id)}`;
  const system = email.source === 'system';
  return (
    <section className="app-outbox-detail" aria-labelledby={headingId}>
      <header className="app-drawer-head">
        <h2 id={headingId} className="app-drawer-title app-outbox-detail-title">
          {email.subject}
        </h2>
        <IconButton icon="action.close" aria-label="Close email" onPress={onClose} />
      </header>
      <div className="app-outbox-detail-body">
        <dl className="app-drawer-facts app-outbox-facts">
          <div className="app-drawer-fact">
            <dt>{system ? 'Sent' : 'Approved and sent'}</dt>
            <dd>{sentFormat.format(new Date(email.sent_at))}</dd>
          </div>
          <div className="app-drawer-fact">
            <dt>To</dt>
            <dd className="app-outbox-recipients">
              {email.to.map((address) => (
                <span key={address}>{address}</span>
              ))}
            </dd>
          </div>
          <div className="app-drawer-fact">
            <dt>Item</dt>
            <dd>
              <ItemLink id={email.item_id} />
            </dd>
          </div>
          {email.requested_by === null || email.approved_by === null ? (
            <div className="app-drawer-fact">
              <dt>From</dt>
              <dd>System mail, not drafted by the assistant</dd>
            </div>
          ) : (
            <>
              <div className="app-drawer-fact">
                <dt>Requested by</dt>
                <dd>{email.requested_by.name}</dd>
              </div>
              <div className="app-drawer-fact">
                <dt>Approved by</dt>
                <dd>{email.approved_by.name}</dd>
              </div>
            </>
          )}
        </dl>
        {!system && email.requested_by?.id === viewer.id && (
          <Button
            size="sm"
            icon="nav.assistant"
            className="app-outbox-thread"
            onPress={() => {
              openAssistantThread(viewer.id, email.thread_id);
            }}
          >
            Open thread
          </Button>
        )}
        {email.html_body === '' ? (
          <pre className="app-outbox-text">{email.body}</pre>
        ) : (
          <iframe
            className="app-outbox-frame"
            title="Email preview"
            sandbox=""
            referrerPolicy="no-referrer"
            srcDoc={email.html_body}
          />
        )}
      </div>
    </section>
  );
}

function OutboxSkeleton() {
  return (
    <div role="status" aria-label="Loading the outbox" aria-busy="true">
      <table className="app-mine-table app-outbox-table" aria-hidden="true">
        <Head columns={COLUMNS} />
        <tbody>
          {Array.from({ length: 6 }, (_, row) => (
            <tr key={row} className="app-outbox-row">
              {COLUMNS.map((column, index) => (
                <td key={column.id} data-col={column.id}>
                  <span
                    className="app-skeleton"
                    style={{ width: `${String(50 + ((row * 17 + index * 29) % 40))}%` }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function OutboxPage({
  selectedId,
  onSelect,
}: {
  selectedId?: number;
  onSelect: (id: number | undefined) => void;
}) {
  const list = useListOutboxEmails();
  const emails = list.data ?? [];
  const selected = emails.find((email) => email.id === selectedId);
  const now = new Date();

  let body: React.ReactNode;
  if (list.isPending) {
    body = <OutboxSkeleton />;
  } else if (list.isError) {
    body = (
      <div className="app-outbox-error" role="alert">
        <EmptyState
          icon="feedback.error"
          title="Couldn't load the outbox."
          action={
            <Button
              size="sm"
              onPress={() => {
                void list.refetch();
              }}
            >
              Retry
            </Button>
          }
        >
          {apiErrorMessage(list.error)}
        </EmptyState>
      </div>
    );
  } else if (emails.length === 0) {
    body = (
      <EmptyState
        icon="nav.outbox"
        title="No emails yet"
        action={
          <Button size="sm" icon="nav.assistant" onPress={openAssistant}>
            Open the assistant
          </Button>
        }
      >
        Emails the assistant drafts land here after you approve them.
      </EmptyState>
    );
  } else {
    const columns = selected === undefined ? COLUMNS : COLUMNS.filter((column) => COMPACT.has(column.id));
    body = (
      <div className="app-outbox-split" data-detail={selected === undefined ? undefined : 'true'}>
        <table className="app-mine-table app-outbox-table" aria-label="Sent emails">
          <Head columns={columns} />
          <tbody>
            {emails.map((email) => (
              <OutboxRow
                key={email.id}
                email={email}
                columns={columns}
                now={now}
                selected={email.id === selectedId}
                onSelect={() => {
                  onSelect(email.id === selectedId ? undefined : email.id);
                }}
              />
            ))}
          </tbody>
        </table>
        {selected !== undefined && (
          <OutboxDetail
            email={selected}
            onClose={() => {
              onSelect(undefined);
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="app-outbox">
      <header className="app-mine-header">
        <h1 className="app-page-title">Outbox</h1>
        <span className="app-muted">Demo mail: nothing leaves ClearPath.</span>
      </header>
      {body}
    </div>
  );
}
