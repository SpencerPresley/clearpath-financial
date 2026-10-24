/*
 * The inbox inside the bell's popover: newest first, grouped Today / Earlier. A React Aria ListBox, so arrow
 * keys move between rows and Enter opens one (onAction); rows aren't links because React Aria's own router
 * isn't wired to TanStack's, and an href would reload the page. Opening the popover puts focus on the newest
 * row, so the first Enter opens it rather than reaching Mark all read.
 */
import { useId, useRef } from 'react';
import { Header, Heading, ListBox, ListBoxItem, ListBoxSection } from 'react-aria-components';

import type { NotificationOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { errorMessage } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import { formatDateTime } from '../../ui/labels';
import { formatAge } from '../../ui/RelativeAge';
import { SkeletonText } from '../../ui/Skeleton';
import { describeNotification } from './text';
import type { useNotifications } from './useNotifications';

const LIMIT = 50; // the API's default page

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function groupByDay(rows: readonly NotificationOut[], now: Date) {
  const today: NotificationOut[] = [];
  const earlier: NotificationOut[] = [];
  for (const row of rows) (sameDay(new Date(row.created_at), now) ? today : earlier).push(row);
  return [
    { id: 'today', label: 'Today', rows: today },
    { id: 'earlier', label: 'Earlier', rows: earlier },
  ].filter((group) => group.rows.length > 0);
}

function Row({ row, now }: { row: NotificationOut; now: Date }) {
  const line = describeNotification(row);
  const at = new Date(row.created_at);
  const unread = row.read_at === null;
  return (
    <ListBoxItem
      id={row.id}
      textValue={line.text}
      className="app-inbox-row"
      data-unread={unread ? 'true' : undefined}
    >
      <span className="app-inbox-dot" aria-hidden="true" />
      <span className="app-inbox-icon" data-tone={line.tone}>
        <Icon name={line.icon} />
      </span>
      <span className="app-inbox-line" title={line.text}>
        {unread && <span className="sr-only">Unread: </span>}
        {line.before && <span className="app-inbox-fixed">{line.before}</span>}
        {line.item && (
          <>
            <span className="app-inbox-key">{line.item.key}</span>
            <span className="app-inbox-fixed">{' · '}</span>
            <span className="app-inbox-title">{line.item.title}</span>
          </>
        )}
        {line.after && <span className="app-inbox-fixed">{line.after}</span>}
      </span>
      <time className="app-inbox-age" dateTime={at.toISOString()} title={formatDateTime(at)}>
        <span aria-hidden="true">{formatAge(at, now)}</span>
        <span className="sr-only">{formatDateTime(at)}</span>
      </time>
    </ListBoxItem>
  );
}

/** Same rhythm as the loaded list (a group header, then rows), so nothing jumps when it arrives. */
function Loading() {
  return (
    <div role="status" aria-label="Loading notifications" className="app-inbox-body">
      <div className="app-inbox-group" aria-hidden="true">
        <SkeletonText width="3rem" />
      </div>
      {[16, 12, 14, 10].map((width) => (
        <div key={width} className="app-inbox-row" aria-hidden="true">
          <span className="app-inbox-dot" />
          <span className="app-skeleton size-4" />
          <SkeletonText width={`${String(width)}rem`} />
          <SkeletonText width="1.5rem" />
        </div>
      ))}
    </div>
  );
}

export interface InboxProps {
  query: ReturnType<typeof useNotifications>;
  onOpenRow: (row: NotificationOut) => void;
  onMarkAllRead: () => void;
  markingAll: boolean;
  /** Reference time for "Today" and ages; defaults to render time. */
  now?: Date;
}

export function Inbox({ query, onOpenRow, onMarkAllRead, markingAll, now = new Date() }: InboxProps) {
  const headingId = useId();
  const list = useRef<HTMLDivElement>(null);
  const page = query.data;
  const unread = page?.unread_count ?? 0;

  const markAllRead = () => {
    // The button goes away once nothing is unread: hand focus to the newest row first, so it isn't dropped.
    list.current?.querySelector<HTMLElement>('[role="option"]')?.focus();
    onMarkAllRead();
  };

  let body;
  if (page === undefined) {
    body = query.isError ? (
      <div className="app-inbox-error" role="alert">
        <Icon name="feedback.error" size={14} />
        <span className="app-inbox-error-text">
          {errorMessage(query.error, 'Couldn’t load notifications. Try again in a moment.')}
        </span>
        <Button size="sm" icon="action.reload" onPress={() => void query.refetch()}>
          Retry
        </Button>
      </div>
    ) : (
      <Loading />
    );
  } else if (page.rows.length === 0) {
    body = (
      <EmptyState icon="nav.notifications" title="No notifications">
        Assignments, decisions, re-reviews, mentions, expiring approvals and partner-page findings show up
        here.
      </EmptyState>
    );
  } else {
    const byId = new Map(page.rows.map((row) => [row.id, row]));
    body = (
      <ListBox
        ref={list}
        aria-labelledby={headingId}
        autoFocus="first"
        className="app-inbox-body"
        selectionMode="none"
        onAction={(key) => {
          const row = byId.get(Number(key));
          if (row !== undefined) onOpenRow(row);
        }}
      >
        {groupByDay(page.rows, now).map((group) => (
          <ListBoxSection key={group.id} id={group.id} className="app-inbox-section">
            <Header className="app-inbox-group">{group.label}</Header>
            {group.rows.map((row) => (
              <Row key={row.id} row={row} now={now} />
            ))}
          </ListBoxSection>
        ))}
      </ListBox>
    );
  }

  return (
    <>
      <div className="app-inbox-head">
        <Heading slot="title" id={headingId} className="app-inbox-heading">
          Notifications
        </Heading>
        {unread > 0 && (
          <>
            <span className="app-inbox-unread">{String(unread)} unread</span>
            <Button
              size="sm"
              variant="ghost"
              icon="action.mark_all_read"
              className="ml-auto"
              isDisabled={markingAll}
              onPress={markAllRead}
            >
              Mark all read
            </Button>
          </>
        )}
      </div>
      {body}
      {page !== undefined && query.isError && (
        <p className="app-inbox-foot" role="status">
          <Icon name="feedback.error" size={14} />
          Couldn’t refresh; showing what loaded earlier.
        </p>
      )}
      {page !== undefined && !query.isError && page.rows.length >= LIMIT && (
        <p className="app-inbox-foot">
          Showing the latest {LIMIT}. Older activity is on each item’s History tab.
        </p>
      )}
    </>
  );
}
