import { Button as AriaButton, Menu, MenuItem, MenuTrigger, Popover } from 'react-aria-components';

import type { ItemRowOut } from '../../api/generated/model';
import { useListUsers } from '../../api/generated/users/users';
import { PickerName, pickerText } from '../../ui/Availability';
import { Icon } from '../../ui/Icon';
import { useQueueCell } from './cellContext';
import { stopRowClick } from './stopRowClick';

function AssigneeName({ row }: { row: ItemRowOut }) {
  return row.assignee === null ? (
    <span className="text-muted">Unassigned</span>
  ) : (
    <span className="truncate">{row.assignee.name}</span>
  );
}

/** Reviewers load only when the menu opens, so a page of rows doesn't each ask for the list. */
function AssignMenu({ row }: { row: ItemRowOut }) {
  const { assign } = useQueueCell();
  const reviewers = useListUsers({ role: 'reviewer' });
  const others = (reviewers.data ?? []).filter((u) => u.id !== row.assignee?.id);
  return (
    <Menu
      className="app-menu"
      aria-label={`Assign ${row.key} to`}
      onAction={(key) => {
        if (key === 'none') {
          assign(row, null, 'Unassigned');
          return;
        }
        const user = others.find((u) => String(u.id) === key);
        if (user !== undefined) assign(row, user.id, user.display_name);
      }}
    >
      {row.assignee !== null && (
        <MenuItem id="none" className="app-menu-item">
          Unassigned
        </MenuItem>
      )}
      {others.map((user) => (
        <MenuItem
          key={user.id}
          id={String(user.id)}
          textValue={pickerText(user.display_name, user.is_available)}
          className="app-menu-item"
        >
          <PickerName name={user.display_name} isAvailable={user.is_available} />
        </MenuItem>
      ))}
    </Menu>
  );
}

/**
 * Assignee (product-spec Queue: edited inline). Leads and admins reassign from a menu; a reviewer can hand off
 * their own item; an unassigned submitted item offers Claim to reviewers. Otherwise the name is plain text.
 */
export function AssigneeCell({ row }: { row: ItemRowOut }) {
  const { canAssign, canClaim, claim, activeId } = useQueueCell();
  const inTabOrder = row.id === activeId;

  if (canAssign(row)) {
    return (
      <span className="app-cell-control w-full" onClick={stopRowClick}>
        <MenuTrigger>
          <AriaButton
            className="app-cell-edit app-cell-edit-wide"
            aria-label={`Assignee for ${row.key}: ${row.assignee?.name ?? 'Unassigned'}. Change`}
            excludeFromTabOrder={!inTabOrder}
          >
            <AssigneeName row={row} />
            <Icon name="action.expand" size={12} className="app-cell-edit-caret" />
          </AriaButton>
          <Popover
            className="app-popover max-h-80 min-w-44 overflow-auto"
            placement="bottom start"
            offset={4}
          >
            <AssignMenu row={row} />
          </Popover>
        </MenuTrigger>
      </span>
    );
  }

  if (canClaim(row)) {
    return (
      // The button alone says it's unassigned and what to do about it; its name carries the item key.
      <span className="app-cell-control" onClick={stopRowClick}>
        <AriaButton
          className="app-btn"
          data-variant="secondary"
          data-size="sm"
          aria-label={`Claim ${row.key}`}
          excludeFromTabOrder={!inTabOrder}
          onPress={() => {
            claim(row);
          }}
        >
          Claim
        </AriaButton>
      </span>
    );
  }

  return <AssigneeName row={row} />;
}
