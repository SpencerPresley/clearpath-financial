/*
 * The assistant side panel (spec §4.3): a complementary region beside the page, not a modal, so the app stays
 * usable while it works. Header: the thread, a switcher over your threads, New thread, Close. A thread is
 * created lazily on the first message, so opening the panel never leaves empty threads behind.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from '@tanstack/react-router';
import { useState } from 'react';
import { Button as AriaButton, Menu, MenuItem, MenuTrigger, Popover } from 'react-aria-components';

import {
  createAssistantThread,
  getListAssistantThreadsQueryKey,
  useListAssistantThreads,
} from '../../api/generated/assistant/assistant';
import type { AssistantThreadOut } from '../../api/generated/model';
import { getListOutboxEmailsQueryKey } from '../../api/generated/notifications/notifications';
import { Icon } from '../../ui/Icon';
import { IconButton } from '../../ui/IconButton';
import type { Role } from '../../ui/domain';
import { useViewer } from '../../ui/layout/Viewer';
import { RelativeAge } from '../../ui/RelativeAge';
import { Composer } from './Composer';
import { readActiveThread, writeActiveThread } from './storage';
import { streamErrorLine, ThreadView } from './ThreadView';

export const ASSISTANT_PANEL_ID = 'assistant-panel';

const UNTITLED = 'Untitled thread';

/** Three short asks for an empty thread, by what the viewer does all day. */
export function exampleAsks(roles: readonly Role[], itemKey: string | undefined): string[] {
  const about = itemKey ?? 'CP-…';
  const precedent = 'Find precedent for “no impact to your credit score”';
  if (roles.includes('reviewer') || roles.includes('lead')) {
    return ["What's waiting on me?", precedent, `Email compliance a summary of ${about}`];
  }
  if (roles.includes('marketer')) {
    return ["What's holding up my submissions?", precedent, `Email compliance a summary of ${about}`];
  }
  return ['What does the queue look like today?', precedent, `Email compliance a summary of ${about}`];
}

function EmptyThread({ asks, onPick }: { asks: readonly string[]; onPick: (text: string) => void }) {
  return (
    <div className="app-assistant-empty">
      <p className="app-assistant-empty-title">Ask about items, findings, precedents or offer terms.</p>
      <p className="app-muted">
        It reads what you can see and drafts emails for you to approve. It can&apos;t decide items.
      </p>
      <ul className="app-assistant-asks" aria-label="Example questions">
        {asks.map((ask) => (
          <li key={ask}>
            <button
              type="button"
              className="app-assistant-ask"
              onClick={() => {
                onPick(ask);
              }}
            >
              {ask}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ThreadMenu({
  threads,
  activeId,
  onSelect,
}: {
  threads: readonly AssistantThreadOut[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <MenuTrigger>
      <AriaButton className="app-btn app-assistant-threads-btn" data-variant="ghost" data-size="sm">
        Threads
        <Icon name="action.expand" size={14} />
      </AriaButton>
      <Popover className="app-popover max-h-80 w-80 overflow-auto" placement="bottom end" offset={4}>
        <Menu
          className="app-menu"
          selectionMode="single"
          selectedKeys={activeId === null ? [] : [activeId]}
          onAction={(key) => {
            onSelect(String(key));
          }}
          renderEmptyState={() => <div className="app-menu-header">No threads yet</div>}
        >
          {threads.map((thread) => (
            <MenuItem
              key={thread.id}
              id={thread.id}
              textValue={thread.title === '' ? UNTITLED : thread.title}
              className="app-menu-item app-assistant-thread-item"
            >
              <span className="app-assistant-thread-title">
                {thread.title === '' ? UNTITLED : thread.title}
              </span>
              {thread.awaiting_approval && (
                <span className="app-assistant-thread-pending">
                  <Icon name="feedback.awaiting" size={12} />
                  Pending approval
                </span>
              )}
              <RelativeAge at={thread.updated_at} />
            </MenuItem>
          ))}
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}

export function AssistantPanel({ onClose, autoFocus }: { onClose: () => void; autoFocus?: boolean }) {
  const viewer = useViewer();
  const queryClient = useQueryClient();
  const params: { itemId?: string } = useParams({ strict: false });
  const itemId =
    params.itemId !== undefined && /^\d+$/.test(params.itemId) ? Number(params.itemId) : undefined;
  const itemKey = itemId === undefined ? undefined : `CP-${String(itemId)}`;

  const threads = useListAssistantThreads();
  const [activeId, setActiveId] = useState<string | null>(() => readActiveThread(viewer.id));
  const [pending, setPending] = useState<string | undefined>(undefined);
  const [draft, setDraft] = useState<{ text: string } | undefined>(undefined);

  const select = (id: string | null) => {
    setPending(undefined);
    setActiveId(id);
    writeActiveThread(viewer.id, id);
  };

  // A remembered thread that's gone (or another user's on a shared browser) falls back to a new one. Threads
  // created in this view count as known even if a list fetch that started earlier lands without them.
  const known = threads.data;
  const [createdIds, setCreatedIds] = useState<readonly string[]>([]);
  const threadId =
    activeId !== null &&
    known !== undefined &&
    !createdIds.includes(activeId) &&
    !known.some((thread) => thread.id === activeId)
      ? null
      : activeId;

  const create = useMutation({
    mutationFn: () => createAssistantThread(),
    onSuccess: (thread) => {
      queryClient.setQueryData<AssistantThreadOut[]>(getListAssistantThreadsQueryKey(), (rows) => [
        thread,
        ...(rows ?? []),
      ]);
    },
  });

  const startThread = (text: string) => {
    create.mutate(undefined, {
      onSuccess: (thread) => {
        setCreatedIds((ids) => [...ids, thread.id]);
        select(thread.id);
        setPending(text);
      },
    });
  };

  const settled = () => {
    void queryClient.invalidateQueries({ queryKey: getListAssistantThreadsQueryKey() });
    void queryClient.invalidateQueries({ queryKey: getListOutboxEmailsQueryKey() });
  };

  const active = known?.find((thread) => thread.id === threadId);
  const title = active === undefined || active.title === '' ? 'New thread' : active.title;
  const asks = exampleAsks(viewer.roles, itemKey);
  const createError = create.isError ? streamErrorLine(create.error) : null;

  return (
    <aside id={ASSISTANT_PANEL_ID} aria-label="Assistant" className="app-assistant">
      <header className="app-assistant-head">
        <h2 className="app-assistant-title" title={title}>
          {title}
        </h2>
        <ThreadMenu threads={known ?? []} activeId={threadId} onSelect={select} />
        <IconButton
          icon="action.new"
          aria-label="New thread"
          size="sm"
          isDisabled={threadId === null}
          onPress={() => {
            select(null);
          }}
        />
        <IconButton icon="action.close" aria-label="Close assistant" size="sm" onPress={onClose} />
      </header>
      {threadId === null ? (
        <>
          <div className="app-assistant-body">
            <EmptyThread
              asks={asks}
              onPick={(text) => {
                setDraft({ text });
              }}
            />
          </div>
          {createError !== null && (
            <p className="app-assistant-error" role="alert">
              {createError}
            </p>
          )}
          <Composer
            onSend={startThread}
            running={false}
            lockedReason={create.isPending ? 'Starting a thread…' : undefined}
            contextKey={itemKey}
            autoFocus={autoFocus}
            draft={draft}
          />
        </>
      ) : (
        <ThreadView
          key={threadId}
          threadId={threadId}
          itemId={itemId}
          pending={pending}
          onPendingSent={() => {
            setPending(undefined);
          }}
          onSettled={settled}
          autoFocus={autoFocus}
          empty={(pick) => <EmptyThread asks={asks} onPick={pick} />}
        />
      )}
    </aside>
  );
}
