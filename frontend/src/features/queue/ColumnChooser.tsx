/*
 * Column chooser: which queue columns show. Choice persists per browser (localStorage) and travels with a
 * saved view. Key and Title can't be hidden: without them a row can't be identified.
 */
import type { Key, Selection } from 'react-aria-components';
import {
  Button as AriaButton,
  Menu,
  MenuItem,
  MenuSection,
  MenuTrigger,
  Popover,
  Separator,
} from 'react-aria-components';

import { Icon } from '../../ui/Icon';
import { COLUMN_IDS, COLUMN_LABELS, DEFAULT_COLUMN_VISIBILITY } from './columns';
import type { ColumnId, ColumnVisibility } from './columns';

export const COLUMNS_KEY = 'clearpath.queue.columns';
const LOCKED: readonly ColumnId[] = ['select', 'key', 'title'];
const CHOOSABLE = COLUMN_IDS.filter((id) => !LOCKED.includes(id)) as Exclude<
  ColumnId,
  'select' | 'key' | 'title'
>[];

export function visibleColumnIds(visibility: ColumnVisibility): string[] {
  return COLUMN_IDS.filter((id) => id !== 'select' && visibility[id] !== false);
}

/** Visibility from a saved view's column list: listed columns show, the rest hide. */
export function visibilityFromColumns(columns: readonly string[]): ColumnVisibility {
  const shown = new Set(columns);
  return Object.fromEntries(CHOOSABLE.map((id) => [id, shown.has(id)]));
}

export function readColumns(): ColumnVisibility {
  try {
    const raw = window.localStorage.getItem(COLUMNS_KEY);
    if (raw === null) return DEFAULT_COLUMN_VISIBILITY;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return DEFAULT_COLUMN_VISIBILITY;
    // Over the defaults, so a column added since the choice was stored starts at its default (hidden).
    return {
      ...DEFAULT_COLUMN_VISIBILITY,
      ...Object.fromEntries(
        Object.entries(parsed).filter((e): e is [string, boolean] => typeof e[1] === 'boolean'),
      ),
    };
  } catch {
    return DEFAULT_COLUMN_VISIBILITY;
  }
}

export function writeColumns(visibility: ColumnVisibility) {
  try {
    window.localStorage.setItem(COLUMNS_KEY, JSON.stringify(visibility));
  } catch {
    // storage blocked: the choice lasts for this page view
  }
}

export function ColumnChooser({
  visibility,
  onChange,
}: {
  visibility: ColumnVisibility;
  onChange: (visibility: ColumnVisibility) => void;
}) {
  const selected = new Set<Key>(CHOOSABLE.filter((id) => visibility[id] !== false));
  return (
    <MenuTrigger>
      <AriaButton className="app-chip-btn app-chip-plain" aria-label="Columns">
        <Icon name="action.columns" size={14} />
        <span>Columns</span>
      </AriaButton>
      <Popover className="app-popover" placement="bottom end" offset={4}>
        <Menu
          className="app-menu"
          aria-label="Columns"
          onAction={(key) => {
            if (key === 'reset') onChange(DEFAULT_COLUMN_VISIBILITY);
          }}
        >
          <MenuSection
            selectionMode="multiple"
            selectedKeys={selected}
            onSelectionChange={(keys: Selection) => {
              const shown = keys === 'all' ? new Set<Key>(CHOOSABLE) : keys;
              onChange(Object.fromEntries(CHOOSABLE.map((id) => [id, shown.has(id)])));
            }}
          >
            {CHOOSABLE.map((id) => (
              <MenuItem
                key={id}
                id={id}
                textValue={COLUMN_LABELS[id]}
                className="app-menu-item app-menu-check"
              >
                {({ isSelected }) => (
                  <>
                    <span className="app-menu-check-mark" aria-hidden="true">
                      {isSelected && <Icon name="action.approve" size={12} />}
                    </span>
                    {COLUMN_LABELS[id]}
                  </>
                )}
              </MenuItem>
            ))}
          </MenuSection>
          <Separator className="app-menu-separator" />
          <MenuItem id="reset" className="app-menu-item">
            Reset columns
          </MenuItem>
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}
