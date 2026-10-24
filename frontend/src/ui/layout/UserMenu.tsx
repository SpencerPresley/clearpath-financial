import {
  Button as AriaButton,
  Header,
  Menu,
  MenuItem,
  MenuSection,
  MenuTrigger,
  Popover,
  Separator,
} from 'react-aria-components';

import { Icon } from '../Icon';
import { initialsOf, useViewer } from './Viewer';

const ROLE_LABELS = { marketer: 'Marketer', reviewer: 'Reviewer', lead: 'Compliance lead', admin: 'Admin' };

export function UserMenu() {
  const viewer = useViewer();
  const roles = viewer.roles.map((role) => ROLE_LABELS[role]).join(', ');

  return (
    <MenuTrigger>
      <AriaButton className="app-user-btn" aria-label={`${viewer.name}, account menu`}>
        <span className="app-avatar" aria-hidden="true">
          {initialsOf(viewer.name)}
        </span>
        <span aria-hidden="true">{viewer.name}</span>
        <Icon name="action.expand" size={14} className="text-brand-muted" />
      </AriaButton>
      <Popover className="app-popover" placement="bottom end" offset={6}>
        <Menu className="app-menu" aria-label="Account">
          <MenuSection>
            <Header className="app-menu-header">
              <div className="font-medium">{viewer.name}</div>
              <div className="text-meta text-muted">{roles}</div>
              {viewer.isDemo && (
                <div className="mt-1 text-meta text-muted">No sign-in yet: demo session with every role.</div>
              )}
            </Header>
          </MenuSection>
          <Separator className="app-menu-separator" />
          <MenuSection>
            <MenuItem className="app-menu-item" isDisabled={viewer.isDemo} textValue="Sign out">
              <Icon name="action.sign_out" />
              <span>Sign out</span>
            </MenuItem>
          </MenuSection>
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}
