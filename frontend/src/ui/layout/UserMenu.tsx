import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Button as AriaButton, Dialog, DialogTrigger, Heading, Popover } from 'react-aria-components';

import { getGetMeQueryKey } from '../../api/generated/me/me';
import { Button } from '../Button';
import { Icon } from '../Icon';
import { showToast } from '../toast';
import { signOut } from './session';
import { initialsOf, useViewer } from './Viewer';

const ROLE_LABELS = { marketer: 'Marketer', reviewer: 'Reviewer', lead: 'Compliance lead', admin: 'Admin' };

/** Account panel: who is signed in, their roles, and sign out. */
export function UserMenu() {
  const viewer = useViewer();
  const qc = useQueryClient();
  const [pending, setPending] = useState(false);
  const roles = viewer.roles.map((role) => ROLE_LABELS[role]).join(', ');

  const doSignOut = () => {
    setPending(true);
    signOut().then(
      () => {
        // Drop everything cached for this user, then let SessionGate find no session and show sign-in.
        qc.removeQueries({ predicate: (q) => q.queryKey[0] !== getGetMeQueryKey()[0] });
        void qc.resetQueries({ queryKey: getGetMeQueryKey() });
      },
      () => {
        setPending(false);
        showToast({
          tone: 'error',
          title: 'Couldn’t sign out',
          description: 'Check your connection and try again.',
        });
      },
    );
  };

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
        <Dialog className="app-menu-header flex flex-col gap-0.5 outline-none" aria-label="Account">
          <Heading slot="title" className="font-medium">
            {viewer.name}
          </Heading>
          <p className="text-meta text-muted">{viewer.email}</p>
          <p className="text-meta text-muted">{roles || 'No roles'}</p>
          <div className="mt-2">
            <Button size="sm" icon="action.sign_out" isDisabled={pending} onPress={doSignOut}>
              Sign out
            </Button>
          </div>
        </Dialog>
      </Popover>
    </DialogTrigger>
  );
}
