/*
 * The topbar's quick-jump: type a CP key, title words or an old tracker ID (MCR-26-045) and open the item. A
 * React Aria ComboBox over `GET /items?q=` (debounced, top 8, every status and legacy imports: `sort=updated`,
 * because the queue sort narrows to open review work). ⌘K / Ctrl+K from anywhere, or `/` outside a field.
 *
 * Results are shown only when they answer what's typed now: while a newer search settles the list says
 * "Searching…", never the previous rows, so Enter can't open an answer to an older question. Enter opens the
 * highlighted result, or the top one (marked ↵) when none is; pressed before the results arrive, it opens the top
 * one as soon as they do. Escape clears the box and puts focus back where ⌘K or / took it from.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { useEffect, useRef, useState } from 'react';
import { ComboBox, Group, Input, ListBox, ListBoxItem, Popover } from 'react-aria-components';
import type { Key } from 'react-aria-components';

import { getListItemsQueryOptions, useListItems } from '../../api/generated/items/items';
import type { ItemRowOut } from '../../api/generated/model';
import { StatusBadge } from '../../ui/badges';
import { errorMessage } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import { focusMain } from '../../ui/layout/focusMain';
import { Kbd } from '../../ui/Kbd';
import { useHotkeys } from '../../ui/useHotkeys';

export const RESULT_LIMIT = 8;
export const DEBOUNCE_MS = 200;
/** Below this, "a" would match half the archive; the box asks for a little more. */
export const MIN_QUERY = 2;
export const QUICK_JUMP_SHORTCUT = 'Meta+K Control+K /';

function useDebounced(value: string, ms: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebounced(value);
    }, ms);
    return () => {
      window.clearTimeout(timer);
    };
  }, [value, ms]);
  return debounced;
}

function isMac(): boolean {
  return /Mac|iPhone|iPad/.test(navigator.userAgent);
}

function Result({ row }: { row: ItemRowOut }) {
  return (
    <ListBoxItem id={row.id} textValue={`${row.key} ${row.title}`} className="app-menu-item app-jump-item">
      <span className="app-jump-key">{row.key}</span>
      <span className="app-jump-title" title={row.title}>
        {row.title}
      </span>
      <span className="app-jump-ref">{row.legacy_ref ?? ''}</span>
      <StatusBadge status={row.status} />
      {/* Shown on the top row while nothing is highlighted (CSS): what Enter will open. */}
      <span className="app-jump-enter" aria-hidden="true">
        <Kbd keys={['↵']} />
      </span>
    </ListBoxItem>
  );
}

type NoteIcon = 'feedback.error' | 'feedback.running';

/** The list's empty state (hint, searching, no match, error), drawn where the results would be. */
function Note({ icon, children }: { icon?: NoteIcon; children: string }) {
  return (
    <p className="app-jump-note" data-state={icon === 'feedback.error' ? 'error' : undefined}>
      {icon && (
        <Icon name={icon} size={14} className={icon === 'feedback.running' ? 'app-spin' : undefined} />
      )}
      {children}
    </p>
  );
}

export function QuickJump() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const [text, setText] = useState('');
  const queryClient = useQueryClient();
  const typed = text.trim();
  const query = useDebounced(typed, DEBOUNCE_MS);
  const enabled = query.length >= MIN_QUERY;
  const results = useListItems(
    { q: query, sort: 'updated', limit: RESULT_LIMIT },
    { query: { enabled, staleTime: 30_000, retry: false } },
  );
  // Only an answer to the text as it stands now.
  const current = enabled && query === typed && results.isSuccess;
  const rows = current ? results.data.rows : [];

  const focusBox = () => {
    const active = document.activeElement;
    if (active instanceof HTMLElement && active !== inputRef.current) returnTo.current = active;
    inputRef.current?.focus();
    inputRef.current?.select();
  };
  useHotkeys({ '/': focusBox });
  useEffect(() => {
    inputRef.current?.setAttribute('aria-keyshortcuts', QUICK_JUMP_SHORTCUT);
    // ⌘K / Ctrl+K works while typing elsewhere too, so it can't go through useHotkeys (which skips modified keys).
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        focusBox();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const open = (row: ItemRowOut) => {
    setText('');
    returnTo.current = null;
    inputRef.current?.blur();
    void navigate({ to: '/items/$itemId', params: { itemId: String(row.id) } }).then(() => {
      focusMain(); // the box was blurred: if it has focus now, ⌘K put it there after the jump
    });
  };

  // Enter before the answer to what's typed came back: ask for it now (no debounce; an identical request in
  // flight is shared) and open its top row, unless the text changed meanwhile. A failure shows in the list.
  const openTopOf = (q: string) => {
    queryClient.query(getListItemsQueryOptions({ q, sort: 'updated', limit: RESULT_LIMIT })).then(
      (page) => {
        const top = page.rows[0];
        if (top !== undefined && inputRef.current?.value.trim() === q) open(top);
      },
      () => undefined,
    );
  };
  const first = rows[0];

  const dismiss = () => {
    setText('');
    const back = returnTo.current;
    returnTo.current = null;
    if (back?.isConnected) back.focus();
    else inputRef.current?.blur();
  };

  const onSelectionChange = (key: Key | null) => {
    const row = rows.find((r) => r.id === key);
    if (row !== undefined) open(row);
  };

  let empty: string;
  let emptyIcon: NoteIcon | undefined;
  if (typed.length < MIN_QUERY) {
    empty = 'Type a CP key, title words or tracker ID.';
  } else if (query === typed && results.isError) {
    empty = errorMessage(results.error, 'Couldn’t search items. Try again in a moment.');
    emptyIcon = 'feedback.error';
  } else if (!current) {
    empty = 'Searching…';
    emptyIcon = 'feedback.running';
  } else {
    empty = `No items match “${query}”.`;
  }
  // React Aria announces "0 options" for an empty list; this says why. Results announce themselves.
  // "Searching…" stays out of it: it would chatter on every keystroke.
  const announcement = text !== '' && rows.length === 0 && emptyIcon !== 'feedback.running' ? empty : '';

  return (
    <ComboBox
      aria-label="Jump to item"
      className="app-search-root"
      items={rows}
      inputValue={text}
      onInputChange={setText}
      value={null}
      onChange={onSelectionChange}
      menuTrigger="input"
      allowsEmptyCollection
      allowsCustomValue
    >
      <Group className="app-search">
        <Icon name="action.search" size={14} />
        <Input
          ref={inputRef}
          placeholder="Jump to item (CP-1042 or title)"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              dismiss();
              return;
            }
            if (event.key !== 'Enter' || event.currentTarget.getAttribute('aria-activedescendant')) return;
            // Enter with nothing highlighted: the top result of what's typed, now or once it arrives.
            event.preventDefault();
            if (first !== undefined) open(first);
            else if (typed.length >= MIN_QUERY && !current) openTopOf(typed);
          }}
        />
        <span className="app-jump-hint" aria-hidden="true">
          <Kbd keys={isMac() ? ['⌘', 'K'] : ['Ctrl', 'K']} />
        </span>
      </Group>
      <Popover className="app-popover app-jump" placement="bottom start" offset={6}>
        {/* Inside the popover: React Aria hides everything else from assistive tech while it's open. */}
        <span className="sr-only" role="status">
          {announcement}
        </span>
        <ListBox<ItemRowOut>
          className="app-menu"
          renderEmptyState={() => <Note icon={emptyIcon}>{empty}</Note>}
        >
          {(row) => <Result row={row} />}
        </ListBox>
      </Popover>
    </ComboBox>
  );
}
