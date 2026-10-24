/*
 * Outbox (decisions.md "Assistant"): the demo's stand-in for real mail. Every row is an email the assistant
 * drafted and a person approved. The HTML part is rendered only inside a sandboxed iframe: `sandbox=""` turns
 * off scripts, forms, popups and same-origin access, so the message can't reach the app or the session.
 */
import { Link } from '@tanstack/react-router';
import { useState } from 'react';

import type { OutboxEmailOut } from '../../../api/generated/model';
import { useListOutboxEmails } from '../../../api/generated/notifications/notifications';
import { Button } from '../../../ui/Button';
import { EmptyState } from '../../../ui/EmptyState';
import { apiErrorMessage } from '../../../ui/forms/apiErrors';
import { IconButton } from '../../../ui/IconButton';
import { RelativeAge } from '../../../ui/RelativeAge';
import { SkeletonTable } from '../../../ui/Skeleton';

/** Sent, To, Subject, Item, Requested by, Approved by. */
const COLUMNS = ['4.5rem', '24%', 'auto', '6rem', '9rem', '9rem'] as const;
const SKELETON_COLUMNS = COLUMNS.map((width) => (width === 'auto' ? '1fr' : width));

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

function OutboxRow({
  email,
  selected,
  onSelect,
  now,
}: {
  email: OutboxEmailOut;
  selected: boolean;
  onSelect: () => void;
  now: Date;
}) {
  const to = email.to.join(', ');
  return (
    <tr className="app-outbox-row" data-selected={selected ? 'true' : undefined}>
      <td className="app-outbox-sent">
        <RelativeAge at={email.sent_at} now={now} />
      </td>
      <td className="app-outbox-to" title={to}>
        {to}
      </td>
      <td className="app-outbox-subject-cell">
        <button type="button" className="app-outbox-subject" aria-pressed={selected} onClick={onSelect}>
          {email.subject}
        </button>
      </td>
      <td>
        <ItemLink id={email.item_id} />
      </td>
      <td className="app-outbox-person">{email.requested_by.name}</td>
      <td className="app-outbox-person">{email.approved_by.name}</td>
    </tr>
  );
}

function OutboxDetail({ email, onClose }: { email: OutboxEmailOut; onClose: () => void }) {
  const headingId = `outbox-email-${String(email.id)}`;
  return (
    <section className="app-outbox-detail" aria-labelledby={headingId}>
      <header className="app-drawer-head">
        <h2 id={headingId} className="app-drawer-title app-outbox-detail-title">
          {email.subject}
        </h2>
        <IconButton icon="action.close" aria-label="Close email" onPress={onClose} />
      </header>
      <div className="app-outbox-detail-body">
        <dl className="app-drawer-facts">
          <div className="app-drawer-fact">
            <dt>Sent</dt>
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
          <div className="app-drawer-fact">
            <dt>Requested by</dt>
            <dd>{email.requested_by.name}</dd>
          </div>
          <div className="app-drawer-fact">
            <dt>Approved by</dt>
            <dd>{email.approved_by.name}</dd>
          </div>
        </dl>
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

export function OutboxPage() {
  const list = useListOutboxEmails();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const emails = list.data ?? [];
  const selected = emails.find((email) => email.id === selectedId);
  const now = new Date();

  let body: React.ReactNode;
  if (list.isPending) {
    body = <SkeletonTable rows={6} columns={SKELETON_COLUMNS} label="Loading the outbox" />;
  } else if (list.isError) {
    body = (
      <div className="app-mine-error" role="alert">
        <p className="app-mine-error-title">Couldn&apos;t load the outbox.</p>
        <p className="app-muted">{apiErrorMessage(list.error)}</p>
        <Button
          size="sm"
          onPress={() => {
            void list.refetch();
          }}
        >
          Retry
        </Button>
      </div>
    );
  } else if (emails.length === 0) {
    body = (
      <EmptyState icon="nav.outbox" title="No emails yet">
        Emails the assistant drafts land here after you approve them.
      </EmptyState>
    );
  } else {
    body = (
      <div className="app-outbox-split">
        <table className="app-mine-table app-outbox-table" aria-label="Sent emails">
          <colgroup>
            {COLUMNS.map((width, index) => (
              <col key={index} style={width === 'auto' ? undefined : { width }} />
            ))}
          </colgroup>
          <thead>
            <tr className="app-outbox-head">
              <th scope="col">Sent</th>
              <th scope="col">To</th>
              <th scope="col">Subject</th>
              <th scope="col">Item</th>
              <th scope="col">Requested by</th>
              <th scope="col">Approved by</th>
            </tr>
          </thead>
          <tbody>
            {emails.map((email) => (
              <OutboxRow
                key={email.id}
                email={email}
                now={now}
                selected={email.id === selectedId}
                onSelect={() => {
                  setSelectedId(email.id === selectedId ? null : email.id);
                }}
              />
            ))}
          </tbody>
        </table>
        {selected !== undefined && (
          <OutboxDetail
            email={selected}
            onClose={() => {
              setSelectedId(null);
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
        {emails.length > 0 && <span className="app-muted">Demo mail: nothing leaves ClearPath.</span>}
      </header>
      {body}
    </div>
  );
}
