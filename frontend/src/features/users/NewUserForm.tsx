/*
 * Add a user, inline above the list (spec §5.7: no modal for a non-destructive form). The server checks the email
 * and the password rules (Django's validators); its 422s land on their fields, anything else on the form's line.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { useCreateUser } from '../../api/generated/admin/admin';
import type { Role, UserOut } from '../../api/generated/model';
import { getListUsersQueryKey } from '../../api/generated/users/users';
import { Button } from '../../ui/Button';
import { ROLES } from '../../ui/domain';
import { fieldErrorsFrom } from '../../ui/forms/apiErrors';
import { CheckboxGroupField, TextInput } from '../../ui/forms/fields';
import { Icon } from '../../ui/Icon';
import { ROLE_NAMES } from './roles';
import { USERS_PARAMS } from './useUserUpdate';

const FIELDS = ['email', 'display_name', 'roles', 'password'] as const;
const ROLE_OPTIONS = ROLES.map((id) => ({ id, label: ROLE_NAMES[id] }));

export function NewUserForm({ onDone }: { onDone: (created: UserOut | null) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [roles, setRoles] = useState<Role[]>([]);
  const [password, setPassword] = useState('');
  const [missing, setMissing] = useState(false);
  const create = useCreateUser({
    mutation: {
      onSuccess: (user) => {
        qc.setQueryData<UserOut[]>(getListUsersQueryKey(USERS_PARAMS), (rows) =>
          rows === undefined ? rows : [...rows, user],
        );
        void qc.invalidateQueries({ queryKey: getListUsersQueryKey() });
        onDone(user);
      },
    },
  });
  const server = create.isError ? fieldErrorsFrom(create.error, FIELDS) : null;
  const formError = server?.form ?? null;
  const errors = {
    display_name: missing && name.trim() === '' ? 'Enter a name.' : server?.fields.display_name,
    email: missing && email.trim() === '' ? 'Enter an email.' : server?.fields.email,
    roles: missing && roles.length === 0 ? 'Pick at least one role.' : server?.fields.roles,
    password: missing && password.length < 12 ? 'At least 12 characters.' : server?.fields.password,
  };

  return (
    <form
      aria-label="New user"
      className="app-users-form"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim() === '' || email.trim() === '' || roles.length === 0 || password.length < 12) {
          setMissing(true);
          return;
        }
        create.mutate({ data: { display_name: name.trim(), email: email.trim(), roles, password } });
      }}
    >
      <TextInput
        label="Name"
        autoFocus
        isRequired
        value={name}
        onChange={setName}
        errorMessage={errors.display_name}
      />
      <TextInput
        label="Email"
        type="email"
        isRequired
        value={email}
        onChange={setEmail}
        errorMessage={errors.email}
      />
      <TextInput
        label="Temporary password"
        type="password"
        isRequired
        value={password}
        onChange={setPassword}
        description="12 characters or more. Share it with them directly."
        errorMessage={errors.password}
      />
      <CheckboxGroupField
        label="Roles"
        isRequired
        value={roles}
        onChange={setRoles}
        options={ROLE_OPTIONS}
        errorMessage={errors.roles}
      />
      <div className="app-users-form-actions">
        <Button type="submit" variant="primary" isDisabled={create.isPending}>
          {create.isPending ? 'Adding…' : 'Add user'}
        </Button>
        <Button
          variant="ghost"
          onPress={() => {
            onDone(null);
          }}
        >
          Cancel
        </Button>
        {formError !== null && (
          <p className="app-import-error-text" role="alert">
            <Icon name="feedback.error" size={14} />
            {formError}
          </p>
        )}
      </div>
    </form>
  );
}
