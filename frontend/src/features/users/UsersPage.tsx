/*
 * Users (spec §1, Admin: Users). Everyone with an account: roles, availability, and whether they can sign in.
 * Each control saves at once with one PATCH (and one audit event server-side). There's always an admin: the
 * server refuses removing the last one or deactivating yourself (409), and the reason shows above the table; your
 * own Deactivate is disabled before you try.
 *
 * Roles are toggles because people hold several (a lead who also reviews). Availability is shown only for people
 * who do review work: it's what auto-assignment reads.
 */
import { useState } from 'react';
import { ToggleButton, ToggleButtonGroup } from 'react-aria-components';
import type { Key } from 'react-aria-components';

import type { Role, UserOut } from '../../api/generated/model';
import { useListUsers } from '../../api/generated/users/users';
import { AwayMark } from '../../ui/Availability';
import { Button } from '../../ui/Button';
import { ROLES } from '../../ui/domain';
import { EmptyState } from '../../ui/EmptyState';
import { errorMessage } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import { plural } from '../../ui/labels';
import { useViewer } from '../../ui/layout/Viewer';
import { SkeletonTable } from '../../ui/Skeleton';
import { Switch } from '../../ui/Switch';
import { showToast } from '../../ui/toast';
import { NewUserForm } from './NewUserForm';
import { doesReviewWork, ROLE_NAMES } from './roles';
import { USERS_PARAMS, useUserUpdate } from './useUserUpdate';

const COLUMNS = ['auto', '20rem', '12rem', '11rem'] as const;

function byActiveThenName(a: UserOut, b: UserOut): number {
  return Number(b.is_active) - Number(a.is_active) || a.display_name.localeCompare(b.display_name);
}

function UserRow({
  user,
  isYou,
  pending,
  onUpdate,
}: {
  user: UserOut;
  isYou: boolean;
  pending: boolean;
  onUpdate: (data: Parameters<ReturnType<typeof useUserUpdate>['update']>[1]) => void;
}) {
  const name = user.display_name || user.email;
  return (
    <tr
      className="app-tr"
      data-inactive={user.is_active ? undefined : 'true'}
      aria-busy={pending || undefined}
    >
      <th scope="row" className="app-td app-users-person">
        <span className="app-users-name">
          {name}
          {isYou && <span className="app-users-you">You</span>}
        </span>
        <span className="app-users-email">{user.email}</span>
      </th>
      <td className="app-td">
        <ToggleButtonGroup
          aria-label={`${name} roles`}
          selectionMode="multiple"
          selectedKeys={new Set<Key>(user.roles)}
          isDisabled={!user.is_active}
          onSelectionChange={(keys) => {
            const next = ROLES.filter((r) => keys.has(r));
            if (next.length === 0) {
              showToast({
                tone: 'error',
                title: 'Everyone needs a role',
                description: 'Deactivate them instead.',
              });
              return;
            }
            onUpdate({ roles: next });
          }}
          className="app-users-roles"
        >
          {ROLES.map((role: Role) => (
            <ToggleButton key={role} id={role} className="app-users-role">
              {ROLE_NAMES[role]}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </td>
      <td className="app-td">
        {doesReviewWork(user.roles) && user.is_active ? (
          // The status text sits inside the switch, so the whole label is the hit area.
          <Switch
            aria-label={`${name} available`}
            isSelected={user.is_available}
            onChange={(is_available) => {
              onUpdate({ is_available });
            }}
          >
            {user.is_available ? <span>Available</span> : <AwayMark />}
          </Switch>
        ) : (
          <span className="text-muted">—</span>
        )}
      </td>
      <td className="app-td">
        <span className="app-users-active">
          {user.is_active ? (
            <>
              <Button
                size="sm"
                variant="ghost"
                className="app-users-deactivate"
                isDisabled={isYou}
                aria-label={`Deactivate ${name}`}
                aria-describedby={isYou ? 'users-self-note' : undefined}
                onPress={() => {
                  onUpdate({ is_active: false });
                }}
              >
                Deactivate
              </Button>
              {isYou && (
                <span id="users-self-note" className="sr-only">
                  You can&apos;t deactivate your own account.
                </span>
              )}
            </>
          ) : (
            <>
              <span className="app-users-deactivated">Deactivated</span>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Reactivate ${name}`}
                onPress={() => {
                  onUpdate({ is_active: true });
                }}
              >
                Reactivate
              </Button>
            </>
          )}
        </span>
      </td>
    </tr>
  );
}

export function UsersPage() {
  const viewer = useViewer();
  const isAdmin = viewer.roles.includes('admin');
  const users = useListUsers(USERS_PARAMS, { query: { enabled: isAdmin } });
  const update = useUserUpdate();
  const [adding, setAdding] = useState(false);

  if (!isAdmin) {
    return (
      <section className="app-users" aria-labelledby="users-title">
        <h1 id="users-title" className="app-page-title">
          Users
        </h1>
        <div className="app-import-panel">
          <EmptyState icon="nav.users" title="Users are managed by admins">
            Ask an admin to add someone or change their roles.
          </EmptyState>
        </div>
      </section>
    );
  }

  let body;
  if (users.isPending) {
    body = (
      <SkeletonTable
        rows={8}
        columns={COLUMNS.map((w) => (w === 'auto' ? '1fr' : w))}
        label="Loading users"
      />
    );
  } else if (users.isError) {
    body = (
      <div className="app-inline-error" role="alert">
        <Icon name="feedback.error" size={14} />
        <span>{errorMessage(users.error, "Couldn't load users.")}</span>
        <Button
          size="sm"
          variant="ghost"
          onPress={() => {
            void users.refetch();
          }}
        >
          Retry
        </Button>
      </div>
    );
  } else {
    const rows = [...users.data].sort(byActiveThenName);
    body = (
      <table className="app-table app-users-table" aria-label="Users">
        <colgroup>
          {COLUMNS.map((w, i) => (
            <col key={i} style={w === 'auto' ? undefined : { width: w }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {['Person', 'Roles', 'Availability', 'Account'].map((h) => (
              <th key={h} className="app-th" scope="col">
                <span className="app-th-label">{h}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((user) => (
            <UserRow
              key={user.id}
              user={user}
              isYou={user.id === viewer.id}
              pending={update.pendingId === user.id}
              onUpdate={(data) => {
                update.update(user.id, data);
              }}
            />
          ))}
        </tbody>
      </table>
    );
  }

  const active = users.data?.filter((u) => u.is_active).length;
  return (
    <section className="app-users" aria-labelledby="users-title">
      <header className="app-users-header">
        <div>
          <h1 id="users-title" className="app-page-title">
            Users
          </h1>
          <p className="app-users-detail">
            {active === undefined ? ' ' : `${plural(active, 'active account')}. `}
            Out-of-office reviewers aren&apos;t auto-assigned new work.
          </p>
        </div>
        {!adding && (
          <Button
            variant="primary"
            icon="action.new"
            onPress={() => {
              setAdding(true);
            }}
          >
            Add user
          </Button>
        )}
      </header>
      {adding && (
        <div className="app-users-create">
          <NewUserForm
            onDone={(created) => {
              setAdding(false);
              if (created !== null) {
                showToast({ title: `Added ${created.display_name}` });
              }
            }}
          />
        </div>
      )}
      {update.error !== null && (
        <p className="app-import-banner" role="alert">
          <Icon name="feedback.error" size={16} />
          Couldn&apos;t change{' '}
          {users.data?.find((u) => u.id === update.error?.userId)?.display_name ?? 'that account'}:{' '}
          {update.error.message}
        </p>
      )}
      <div className="app-import-panel">{body}</div>
    </section>
  );
}
