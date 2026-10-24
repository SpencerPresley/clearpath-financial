/*
 * The topbar's quick-jump: type a CP key, title words or an old tracker ID (MCR-26-045) and open the item. A
 * React Aria ComboBox over `GET /items?q=` (debounced, top 8, every status and legacy imports: `sort=updated`,
 * because the queue sort narrows to open review work). ⌘K / Ctrl+K from anywhere, or `/` outside a field.
 * Enter opens the highlighted result, or the top one when none is highlighted.
 */
import { keepPreviousData } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { useEffect, useRef, useState } from 'react';
import { ComboBox, Input, ListBox, ListBoxItem, Popover } from 'react-aria-components';
import type { Key } from 'react-aria-components';

import { useListItems } from '../../api/generated/items/items';
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
      <span className="app-jump-title">{row.title}</span>
      {row.legacy_ref && <span className="app-jump-ref">{row.legacy_ref}</span>}
      <StatusBadge status={row.status} />
    </ListBoxItem>
  );
}

/**
 * The list's empty state (hint, searching, no match, error). React Aria renders it inside the listbox as its only
 * option, so it's read where the results would be; no live-region role of its own.
 */
function Note({ icon, children }: { icon?: 'feedback.error' | 'feedback.running'; children: string }) {
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
  const [text, setText] = useState('');
  const query = useDebounced(text.trim(), DEBOUNCE_MS);
  const enabled = query.length >= MIN_QUERY;
  const results = useListItems(
    { q: query, sort: 'updated', limit: RESULT_LIMIT },
    { query: { enabled, placeholderData: keepPreviousData, staleTime: 30_000, retry: false } },
  );
  const rows = enabled ? (results.data?.rows ?? []) : [];
  const settling = text.trim() !== query; // typed, debounce not yet fired

  const focusBox = () => {
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
    inputRef.current?.blur();
    void navigate({ to: '/items/$itemId', params: { itemId: String(row.id) } }).then(() => {
      focusMain();
    });
  };

  const onSelectionChange = (key: Key | null) => {
    const row = rows.find((r) => r.id === key);
    if (row !== undefined) open(row);
  };

  let empty: string;
  let emptyIcon: 'feedback.error' | 'feedback.running' | undefined;
  if (!enabled) {
    empty = 'Type a CP key, title words or tracker ID.';
  } else if (results.isError) {
    empty = errorMessage(results.error, 'Couldn’t search items. Try again in a moment.');
    emptyIcon = 'feedback.error';
  } else if (results.isPending || settling || results.isPlaceholderData) {
    empty = 'Searching…';
    emptyIcon = 'feedback.running';
  } else {
    empty = `No items match “${query}”.`;
  }

  return (
    <ComboBox
      aria-label="Jump to item"
      className="app-search"
      items={rows}
      inputValue={text}
      onInputChange={setText}
      value={null}
      onChange={onSelectionChange}
      menuTrigger="input"
      allowsEmptyCollection
      allowsCustomValue
    >
      <Icon name="action.search" size={14} />
      <Input
        ref={inputRef}
        placeholder="Jump to item (CP-1042 or title)"
        onKeyDown={(event) => {
          // Enter with nothing highlighted opens the top result: typing "CP-1042⏎" should just go there.
          const first = rows[0];
          if (
            event.key === 'Enter' &&
            first !== undefined &&
            !event.currentTarget.getAttribute('aria-activedescendant')
          ) {
            event.preventDefault();
            open(first);
          }
          if (event.key === 'Escape' && text === '') inputRef.current?.blur();
        }}
      />
      <span className="app-jump-hint" aria-hidden="true">
        <Kbd keys={isMac() ? ['⌘', 'K'] : ['Ctrl', 'K']} />
      </span>
      <Popover className="app-popover app-jump" placement="bottom start" offset={6}>
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
