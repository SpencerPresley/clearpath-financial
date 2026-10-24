import { useQueryClient } from '@tanstack/react-query';
import type { Query } from '@tanstack/react-query';
import { useRouter } from '@tanstack/react-router';
import { useState } from 'react';
import { Button as AriaButton, Dialog, DialogTrigger, Heading, Popover } from 'react-aria-components';

import { getGetMeQueryKey } from '../../api/generated/me/me';
import { Button } from '../Button';
import { Icon } from '../Icon';
import { forgetQueueTrail } from '../queueTrail';
import { showToast } from '../toast';
import { AvailabilityToggle } from './AvailabilityToggle';
import { signOut } from './session';
import { landingFor } from './landing';
import { ResetDemoDialog } from './ResetDemo';
import { initialsOf, useViewer } from './Viewer';

const ROLE_LABELS = { marketer: 'Marketer', reviewer: 'Reviewer', lead: 'Compliance lead', admin: 'Admin' };

/** Account panel: who is signed in, their roles, and sign out. */
export function UserMenu() {
  const viewer = useViewer();
  const qc = useQueryClient();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const roles = viewer.roles.map((role) => ROLE_LABELS[role]).join(', ');

  const doSignOut = () => {
    setPending(true);
    signOut().then(
      async () => {
        // SessionGate finds no session, shows sign-in and drops what this person left behind. Then clear the URL
        // (at "/" while still signed in, the index route would bounce to this person's landing): the next person
        // starts from "/", not from this person's screen.
        await qc.resetQueries({ queryKey: getGetMeQueryKey() });
        await router.navigate({ to: '/', replace: true });
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

  // Everything cached describes data the reset deleted (an import job, an item): leave the screen for the
  // landing page, then drop the old cache. The person and the session survive a reset, so /api/me stays and the
  // shell doesn't blank. Leaving first means the old screen can't refetch what no longer exists.
  const afterReset = async () => {
    const notMe = (q: Query) => q.queryKey[0] !== getGetMeQueryKey()[0];
    await router.navigate({ to: landingFor(viewer.roles), replace: true });
    qc.getMutationCache().clear();
    forgetQueueTrail(); // its rows were deleted with the old data
    qc.removeQueries({ type: 'inactive', predicate: notMe });
    await qc.resetQueries({ predicate: notMe });
  };

  const isAdmin = viewer.roles.includes('admin');
  const [menuOpen, setMenuOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);

  return (
    <>
      <DialogTrigger isOpen={menuOpen} onOpenChange={setMenuOpen}>
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
            <AvailabilityToggle />
            <div className="mt-2 flex gap-2">
              <Button size="sm" icon="action.sign_out" isDisabled={pending} onPress={doSignOut}>
                Sign out
              </Button>
              {isAdmin && (
                <Button
                  size="sm"
                  icon="action.reset_demo"
                  onPress={() => {
                    setMenuOpen(false);
                    setResetOpen(true);
                  }}
                >
                  Reset demo…
                </Button>
              )}
            </div>
          </Dialog>
        </Popover>
      </DialogTrigger>
      {isAdmin && <ResetDemoDialog isOpen={resetOpen} onOpenChange={setResetOpen} onDone={afterReset} />}
    </>
  );
}
