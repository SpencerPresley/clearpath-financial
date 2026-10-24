import { Button as AriaButton, Dialog, DialogTrigger, Heading, Popover } from 'react-aria-components';

import { Icon } from '../Icon';
import { initialsOf, useViewer } from './Viewer';

const ROLE_LABELS = { marketer: 'Marketer', reviewer: 'Reviewer', lead: 'Compliance lead', admin: 'Admin' };

/**
 * Account panel. A popover dialog rather than a menu: until sign-in exists there is no account action to
 * offer, and a menu whose only item is a disabled "Sign out" is an inert control. When accounts land,
 * sign-out goes here (and this can become a MenuTrigger again).
 */
export function UserMenu() {
  const viewer = useViewer();
  const roles = viewer.roles.map((role) => ROLE_LABELS[role]).join(', ');

  return (
    <DialogTrigger>
      <AriaButton className="app-user-btn" aria-label={`${viewer.name}, account`}>
        <span className="app-avatar" aria-hidden="true">
          {initialsOf(viewer.name)}
        </span>
        <span aria-hidden="true">{viewer.name}</span>
        <Icon name="action.expand" size={14} className="text-brand-muted" />
      </AriaButton>
      <Popover className="app-popover" placement="bottom end" offset={6}>
        <Dialog className="app-menu-header outline-none" aria-label="Account">
          <Heading slot="title" className="font-medium">
            {viewer.name}
          </Heading>
          <p className="text-meta text-muted">{roles}</p>
          {viewer.isDemo === true && (
            <p className="mt-2 max-w-60 text-meta text-muted">
              No sign-in yet. This is a demo session with every role, so every section is visible.
            </p>
          )}
        </Dialog>
      </Popover>
    </DialogTrigger>
  );
}
