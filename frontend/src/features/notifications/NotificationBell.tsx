/*
 * The topbar bell and its popover inbox (spec §4.3 Notifications: in-app only). The count is the polled list's
 * unread_count. A failed poll leaves the bell quiet (no count, no alarm); the error shows inside the inbox.
 */
import { useNavigate } from '@tanstack/react-router';
import { useState } from 'react';
import { Button as AriaButton, Dialog, DialogTrigger, Popover } from 'react-aria-components';

import type { NotificationOut } from '../../api/generated/model';
import { Icon } from '../../ui/Icon';
import { Tooltip } from '../../ui/Tooltip';
import { Inbox } from './Inbox';
import { notificationLink } from './text';
import { useMarkAllRead, useMarkRead, useNotifications } from './useNotifications';

export function countLabel(unread: number): string {
  return unread > 99 ? '99+' : String(unread);
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const notifications = useNotifications();
  const markRead = useMarkRead();
  const markAllRead = useMarkAllRead();
  const unread = notifications.data?.unread_count ?? 0;
  const label = unread > 0 ? `Notifications, ${String(unread)} unread` : 'Notifications';

  const openRow = (row: NotificationOut) => {
    if (row.read_at === null) markRead.mutate({ notificationId: row.id });
    const link = notificationLink(row);
    if (link === null) return; // nothing to open: marking it read is the whole action
    setOpen(false);
    void navigate({ to: '/items/$itemId', params: { itemId: link.itemId }, search: link.search });
  };

  return (
    <DialogTrigger isOpen={open} onOpenChange={setOpen}>
      <Tooltip content="Notifications" placement="bottom">
        <AriaButton
          className="app-topbar-btn app-bell"
          aria-label={label}
          data-active={open ? 'true' : undefined}
        >
          <Icon name="nav.notifications" size={18} />
          {unread > 0 && (
            <span className="app-bell-count" aria-hidden="true">
              {countLabel(unread)}
            </span>
          )}
        </AriaButton>
      </Tooltip>
      <Popover className="app-popover app-inbox" placement="bottom end" offset={6}>
        <Dialog className="app-inbox-dialog" aria-label="Notifications">
          <Inbox
            query={notifications}
            onOpenRow={openRow}
            onMarkAllRead={() => {
              markAllRead.mutate();
            }}
            markingAll={markAllRead.isPending}
          />
        </Dialog>
      </Popover>
    </DialogTrigger>
  );
}
