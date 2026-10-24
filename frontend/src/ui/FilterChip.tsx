/*
 * A filter chip: names its choice ("Product: Credit card, Personal loan") so active filters read as a sentence,
 * opens a checkable menu, and has its own clear button. Same look and behavior as the queue's chips (which
 * predate this shared copy); the classes are theme.css's app-chip family.
 */
import type { Key, Selection } from 'react-aria-components';
import { Button as AriaButton, Menu, MenuItem, MenuTrigger, Popover } from 'react-aria-components';

import { Icon } from './Icon';
import { IconButton } from './IconButton';

export interface ChipOption {
  id: string;
  label: string;
}

export interface FilterChipProps {
  label: string;
  options: readonly ChipOption[];
  selected: readonly string[];
  mode?: 'multiple' | 'single';
  onChange: (ids: string[]) => void;
}

export function chipText(label: string, options: readonly ChipOption[], selected: readonly string[]) {
  if (selected.length === 0) return label;
  const names = selected.map((id) => options.find((o) => o.id === id)?.label ?? id);
  const shown = names.slice(0, 2).join(', ');
  return names.length > 2 ? `${label}: ${shown} +${String(names.length - 2)}` : `${label}: ${shown}`;
}

function keysOf(selection: Selection): string[] {
  return selection === 'all' ? [] : [...selection].map(String);
}

export function FilterChip({ label, options, selected, mode = 'multiple', onChange }: FilterChipProps) {
  const active = selected.length > 0;
  return (
    <span className="app-chip" data-active={active ? 'true' : undefined}>
      <MenuTrigger>
        <AriaButton className="app-chip-btn">
          <span className="truncate">{chipText(label, options, selected)}</span>
          <Icon name="action.expand" size={12} />
        </AriaButton>
        <Popover className="app-popover max-h-80 overflow-auto" placement="bottom start" offset={4}>
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
                      {isSelected && <Icon name="action.check" size={12} />}
                    </span>
                    {option.label}
                  </>
                )}
              </MenuItem>
            )}
          </Menu>
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
