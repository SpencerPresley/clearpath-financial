/*
 * Filter bar (not spreadsheet column menus): a search box, chips for Status, Risk, Assignee, and Partner, and
 * More filters for the rest (each joins the bar as a chip once it has a value). A chip
 * names its choice ("Status: In review, Submitted") so the active filters read as a sentence, and each has its
 * own clear button. Everything writes to the URL through onChange.
 */
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { Key, Selection } from 'react-aria-components';
import {
  Button as AriaButton,
  Input,
  Menu,
  MenuItem,
  MenuTrigger,
  Popover,
  SearchField,
  SubmenuTrigger,
} from 'react-aria-components';

import { useListPartners } from '../../api/generated/partners/partners';
import { Channel, ItemStatus, Product, ReopenReason, RiskTier } from '../../api/generated/model';
import type { ItemSort } from '../../api/generated/model';
import { useListUsers } from '../../api/generated/users/users';
import { STATUS_META } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { cx } from '../../ui/cx';
import { Icon } from '../../ui/Icon';
import { IconButton } from '../../ui/IconButton';
import { CHANNEL_LABEL, PRODUCT_LABEL, REOPEN_REASON_LABEL } from './labels';
import { activeView, hasFilters } from './search';
import type { QueueSearch } from './search';

export interface ChipOption {
  id: string;
  label: string;
}

/** Exhaustive on purpose: a new server sort doesn't compile until someone names it. Menu order is this order. */
export const SORT_LABEL: Record<ItemSort, string> = {
  queue: 'Queue order',
  oldest: 'Oldest first',
  newest: 'Newest first',
  updated: 'Recently updated',
  title: 'Title A–Z',
  title_desc: 'Title Z–A',
  status: 'Status, submitted first',
  status_desc: 'Status, closed first',
  risk_tier: 'Risk, low to high',
  risk_tier_desc: 'Risk, high to low',
  assignee: 'Assignee A–Z',
  assignee_desc: 'Assignee Z–A',
  partner: 'Partner A–Z',
  partner_desc: 'Partner Z–A',
  open_findings: 'Fewest findings first',
  open_findings_desc: 'Most findings first',
  round: 'Round, first to latest',
  round_desc: 'Round, latest first',
};

const SORT_HINT: Partial<Record<ItemSort, string>> = {
  queue: 'Re-reviews, then risk, then age',
};

const RISK_SHORT: Record<RiskTier, string> = { high: 'High', medium: 'Medium', low: 'Low' };
const WAITING_DAYS = [1, 3, 7, 14] as const;

function waitingLabel(days: number) {
  return `>${String(days)} ${days === 1 ? 'day' : 'days'}`;
}

function chipText(label: string, options: readonly ChipOption[], selected: readonly string[]) {
  if (selected.length === 0) return label;
  const names = selected.map((id) => options.find((o) => o.id === id)?.label ?? id);
  const shown = names.slice(0, 2).join(', ');
  return names.length > 2 ? `${label}: ${shown} +${String(names.length - 2)}` : `${label}: ${shown}`;
}

function keysOf(selection: Selection): string[] {
  return selection === 'all' ? [] : [...selection].map(String);
}

interface ChipProps {
  label: string;
  options: readonly ChipOption[];
  selected: readonly string[];
  mode?: 'multiple' | 'single';
  onChange: (ids: string[]) => void;
}

function ChipMenu({ label, options, selected, mode = 'multiple', onChange }: ChipProps) {
  return (
    <Menu
      className="app-menu"
      aria-label={label}
      selectionMode={mode}
      selectedKeys={new Set<Key>(selected)}
      onSelectionChange={(keys) => {
        onChange(keysOf(keys));
      }}
      items={options}
    >
      {(option) => (
        <MenuItem id={option.id} textValue={option.label} className="app-menu-item app-menu-check">
          {({ isSelected }) => (
            <>
              <span className="app-menu-check-mark" aria-hidden="true">
                {isSelected && <Icon name="action.approve" size={12} />}
              </span>
              {option.label}
            </>
          )}
        </MenuItem>
      )}
    </Menu>
  );
}

export function FilterChip(props: ChipProps) {
  const { label, options, selected, onChange } = props;
  const active = selected.length > 0;
  return (
    <span className="app-chip" data-active={active ? 'true' : undefined}>
      <MenuTrigger>
        <AriaButton className="app-chip-btn">
          <span className="truncate">{chipText(label, options, selected)}</span>
          <Icon name="action.expand" size={12} />
        </AriaButton>
        <Popover className="app-popover max-h-80 overflow-auto" placement="bottom start" offset={4}>
          <ChipMenu {...props} />
        </Popover>
      </MenuTrigger>
      {active && (
        <IconButton
          icon="action.close"
          size="sm"
          tooltip={false}
          aria-label={`Clear ${label} filter`}
          className="app-chip-clear"
          onPress={() => {
            onChange([]);
          }}
        />
      )}
    </span>
  );
}

function QueueSearchField({
  value,
  onChange,
}: {
  value: string | undefined;
  onChange: (q: string | undefined) => void;
}) {
  const [text, setText] = useState(value ?? '');
  const emitted = useRef(value ?? '');

  // Follow outside changes (Clear filters, a view switch) but never clobber what's being typed.
  useEffect(() => {
    const incoming = value ?? '';
    if (incoming !== emitted.current) {
      emitted.current = incoming;
      setText(incoming);
    }
  }, [value]);

  useEffect(() => {
    const q = text.trim();
    if (q === emitted.current) return;
    const timer = window.setTimeout(() => {
      emitted.current = q;
      onChange(q === '' ? undefined : q);
    }, 250);
    return () => {
      window.clearTimeout(timer);
    };
  }, [text, onChange]);

  return (
    <SearchField aria-label="Search the queue" value={text} onChange={setText} className="app-queue-search">
      <Icon name="action.search" size={14} className="text-muted" />
      <Input className="app-queue-search-input" placeholder="Title or CP-1042" />
    </SearchField>
  );
}

export interface FilterBarProps {
  search: QueueSearch;
  onChange: (patch: Partial<QueueSearch>) => void;
  /** Back to the current view's own filters. */
  onClear: () => void;
  /** Whether the filters differ from the active view; computed for built-in views when omitted. */
  isModified?: boolean;
  /** The board's columns are statuses, so it has no Status filter. */
  hideStatus?: boolean;
  /** View actions (Modified, Save view) and the saved-views error, after the chips. */
  trailing?: ReactNode;
}

export function FilterBar({
  search,
  onChange,
  onClear,
  isModified,
  hideStatus = false,
  trailing,
}: FilterBarProps) {
  const users = useListUsers({ role: 'reviewer' });
  const partners = useListPartners();
  const view = activeView(search, []);
  const modified = isModified ?? (view.kind === 'custom' ? hasFilters(search) : view.modified);

  const people: ChipOption[] = [
    { id: 'me', label: 'Me' },
    { id: 'none', label: 'Unassigned' },
    ...(users.data ?? []).map((u) => ({ id: `u:${String(u.id)}`, label: u.display_name })),
  ];
  const assignee = search.mine
    ? ['me']
    : search.unassigned
      ? ['none']
      : (search.assignee_id ?? []).map((id) => `u:${String(id)}`);

  const findings =
    search.has_open_findings === undefined ? [] : [search.has_open_findings ? 'open' : 'clear'];

  // The latest onChange is read through a ref, so the search box's debounce effect doesn't restart per render.
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  });
  const [setQ] = useState(() => (q: string | undefined) => {
    onChangeRef.current({ q });
  });

  // Less-used filters live under More filters until they have a value, so the bar stays one line (§5.3).
  const secondary: ChipProps[] = [
    {
      label: 'Product',
      options: Object.values(Product).map((p) => ({ id: p, label: PRODUCT_LABEL[p] })),
      selected: search.product ?? [],
      onChange: (ids) => {
        onChange({ product: ids.length > 0 ? (ids as Product[]) : undefined });
      },
    },
    {
      label: 'Channel',
      options: Object.values(Channel).map((c) => ({ id: c, label: CHANNEL_LABEL[c] })),
      selected: search.channel ?? [],
      onChange: (ids) => {
        onChange({ channel: ids.length > 0 ? (ids as Channel[]) : undefined });
      },
    },
    {
      label: 'Findings',
      mode: 'single',
      options: [
        { id: 'open', label: 'Has open findings' },
        { id: 'clear', label: 'No open findings' },
      ],
      selected: findings,
      onChange: (ids) => {
        onChange({ has_open_findings: ids[0] === undefined ? undefined : ids[0] === 'open' });
      },
    },
    {
      label: 'Waiting',
      mode: 'single',
      options: WAITING_DAYS.map((d) => ({ id: String(d), label: waitingLabel(d) })),
      selected: search.waiting === undefined ? [] : [String(search.waiting)],
      onChange: (ids) => {
        onChange({ waiting: ids[0] === undefined ? undefined : Number(ids[0]) });
      },
    },
    {
      label: 'Re-review reason',
      options: Object.values(ReopenReason).map((r) => ({ id: r, label: REOPEN_REASON_LABEL[r] })),
      selected: search.reopen_reason ?? [],
      onChange: (ids) => {
        onChange({ reopen_reason: ids.length > 0 ? (ids as ReopenReason[]) : undefined });
      },
    },
  ];

  return (
    <div className="app-filter-bar" role="group" aria-label="Filters">
      <QueueSearchField value={search.q} onChange={setQ} />
      {!hideStatus && (
        <FilterChip
          label="Status"
          options={Object.values(ItemStatus).map((s) => ({ id: s, label: STATUS_META[s].label }))}
          selected={search.status ?? []}
          onChange={(ids) => {
            onChange({ status: ids.length > 0 ? (ids as ItemStatus[]) : undefined });
          }}
        />
      )}
      <FilterChip
        label="Risk"
        options={Object.values(RiskTier).map((t) => ({ id: t, label: RISK_SHORT[t] }))}
        selected={search.risk_tier ?? []}
        onChange={(ids) => {
          onChange({ risk_tier: ids.length > 0 ? (ids as RiskTier[]) : undefined });
        }}
      />
      <FilterChip
        label="Assignee"
        mode="single"
        options={people}
        selected={assignee}
        onChange={(ids) => {
          const id = ids[0];
          onChange({
            mine: id === 'me' ? true : undefined,
            unassigned: id === 'none' ? true : undefined,
            assignee_id: id?.startsWith('u:') === true ? [Number(id.slice(2))] : undefined,
          });
        }}
      />
      <FilterChip
        label="Partner"
        options={(partners.data ?? []).map((p) => ({ id: String(p.id), label: p.name }))}
        selected={(search.partner_id ?? []).map(String)}
        onChange={(ids) => {
          onChange({ partner_id: ids.length > 0 ? ids.map(Number) : undefined });
        }}
      />
      {secondary
        .filter((chip) => chip.selected.length > 0)
        .map((chip) => (
          <FilterChip key={chip.label} {...chip} />
        ))}
      <MoreFilters chips={secondary} />
      {modified && (
        <Button size="sm" variant="ghost" onPress={onClear}>
          Clear filters
        </Button>
      )}
      {trailing}
    </div>
  );
}

const isEmpty = (chip: ChipProps) => chip.selected.length === 0;

/**
 * Filters without a value, each a submenu with the same choices its chip has.
 *
 * The list is frozen while the menu is open. A pick gives that filter a value, which would otherwise drop
 * its submenu trigger out of the list and unmount the submenu that holds focus. Focus would land on <body>
 * (where Escape reaches no menu) and the root menu could stay open with nothing able to close it from the
 * keyboard; it would also end a multi-select after one choice. The filter moves to the bar on close.
 */
function MoreFilters({ chips }: { chips: readonly ChipProps[] }) {
  const [frozen, setFrozen] = useState<readonly string[] | null>(null);
  const shown = frozen ? chips.filter((chip) => frozen.includes(chip.label)) : chips.filter(isEmpty);
  if (shown.length === 0) return null;
  return (
    <MenuTrigger
      onOpenChange={(open) => {
        setFrozen(open ? chips.filter(isEmpty).map((chip) => chip.label) : null);
      }}
    >
      <AriaButton className="app-chip-btn app-chip-plain app-filter-more">
        <Icon name="action.filter" size={14} />
        <span>More filters</span>
        <Icon name="action.expand" size={12} />
      </AriaButton>
      <Popover className="app-popover" placement="bottom start" offset={4}>
        <Menu className="app-menu" aria-label="More filters">
          {shown.map((chip) => (
            <SubmenuTrigger key={chip.label}>
              <MenuItem id={chip.label} textValue={chip.label} className="app-menu-item justify-between">
                <span>{chip.label}</span>
                <Icon name="action.expand" size={12} className="-rotate-90 text-muted" />
              </MenuItem>
              <Popover className="app-popover max-h-80 overflow-auto" offset={-4}>
                <ChipMenu {...chip} />
              </Popover>
            </SubmenuTrigger>
          ))}
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}

export function SortMenu({ sort, onChange }: { sort: ItemSort; onChange: (sort: ItemSort) => void }) {
  const options = Object.keys(SORT_LABEL) as ItemSort[];
  return (
    <MenuTrigger>
      <AriaButton className={cx('app-chip-btn app-chip-plain')} aria-label={`Sort: ${SORT_LABEL[sort]}`}>
        <Icon name="action.sort" size={14} />
        <span>{SORT_LABEL[sort]}</span>
        <Icon name="action.expand" size={12} />
      </AriaButton>
      <Popover className="app-popover" placement="bottom end" offset={4}>
        <Menu
          className="app-menu"
          aria-label="Sort"
          selectionMode="single"
          selectedKeys={new Set<Key>([sort])}
          disallowEmptySelection
          onSelectionChange={(keys) => {
            const next = keysOf(keys)[0] as ItemSort | undefined;
            if (next !== undefined) onChange(next);
          }}
        >
          {options.map((option) => (
            <MenuItem
              key={option}
              id={option}
              textValue={SORT_LABEL[option]}
              className="app-menu-item app-menu-check"
            >
              {({ isSelected }) => (
                <>
                  <span className="app-menu-check-mark" aria-hidden="true">
                    {isSelected && <Icon name="action.approve" size={12} />}
                  </span>
                  <span className="flex flex-col">
                    <span>{SORT_LABEL[option]}</span>
                    {SORT_HINT[option] !== undefined && (
                      <span className="text-meta text-muted">{SORT_HINT[option]}</span>
                    )}
                  </span>
                </>
              )}
            </MenuItem>
          ))}
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}
