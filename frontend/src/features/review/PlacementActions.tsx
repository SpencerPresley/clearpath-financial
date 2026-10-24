/*
 * Recording and changing placements (product-spec "Placements"). The submitter or a lead records and edits them,
 * on an approved item; the submitter, a reviewer or an admin confirms a requested takedown. The backend decides;
 * these rules only decide what to offer. Confirming a takedown can't be undone, so it asks first (spec §5.7).
 */
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { getGetItemDriftQueryKey } from '../../api/generated/drift/drift';
import {
  getGetItemHistoryQueryKey,
  getGetItemQueryKey,
  getListPlacementsQueryKey,
  useConfirmTakedown,
  useRecordPlacement,
  useUpdatePlacement,
} from '../../api/generated/items/items';
import type { PlacementOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { ModalDialog } from '../../ui/Dialog';
import { apiErrorMessage, fieldErrorsFrom } from '../../ui/forms/apiErrors';
import { CheckboxField, TextInput } from '../../ui/forms/fields';
import { useViewer } from '../../ui/layout/Viewer';
import { showToast } from '../../ui/toast';

const FIELD_NAMES = ['location', 'url', 'first_run', 'last_run', 'monitored'] as const;

/** Mirrors the backend rules: the submitter, a lead or an admin records and edits placements. */
export function useCanEditPlacements(ownerId: number | null): boolean {
  const viewer = useViewer();
  return viewer.id === ownerId || viewer.roles.some((r) => r === 'lead' || r === 'admin');
}

/** The submitter, a reviewer or an admin confirms a takedown. */
export function useCanConfirmTakedown(ownerId: number | null): boolean {
  const viewer = useViewer();
  return viewer.id === ownerId || viewer.roles.some((r) => r === 'reviewer' || r === 'admin');
}

function useRefreshPlacements(itemId: number) {
  const queryClient = useQueryClient();
  return () => {
    for (const queryKey of [
      getListPlacementsQueryKey(itemId),
      getGetItemDriftQueryKey(itemId),
      getGetItemQueryKey(itemId),
      getGetItemHistoryQueryKey(itemId),
    ]) {
      void queryClient.invalidateQueries({ queryKey });
    }
  };
}

interface FormState {
  location: string;
  url: string;
  first_run: string;
  last_run: string;
  monitored: boolean;
}

function PlacementForm({
  itemId,
  placement,
  onDone,
}: {
  itemId: number;
  placement?: PlacementOut;
  onDone: () => void;
}) {
  const refresh = useRefreshPlacements(itemId);
  const [values, setValues] = useState<FormState>({
    location: placement?.location ?? '',
    url: placement?.url ?? '',
    first_run: placement?.first_run ?? '',
    last_run: placement?.last_run ?? '',
    monitored: placement?.monitored ?? false,
  });
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setValues((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  };

  const mutation = {
    onSuccess: () => {
      refresh();
      showToast({ title: placement === undefined ? 'Placement added' : 'Placement updated' });
      onDone();
    },
    onError: (error: unknown) => {
      // A 422's issues go on their fields; anything else is one line, here and in a toast.
      const { fields, form } = fieldErrorsFrom(error, FIELD_NAMES);
      setErrors(fields);
      setFormError(form);
      if (form !== null)
        showToast({ title: "Couldn't save the placement", description: form, tone: 'error' });
    },
  };
  const record = useRecordPlacement({ mutation });
  const update = useUpdatePlacement({ mutation });

  const submit = () => {
    setFormError(null);
    const lastRun = values.last_run === '' ? null : values.last_run;
    if (placement !== undefined) {
      update.mutate({ placementId: placement.id, data: { last_run: lastRun, monitored: values.monitored } });
      return;
    }
    const missing: Record<string, string> = {};
    if (values.location.trim() === '') missing.location = 'Say where it runs.';
    if (values.first_run === '') missing.first_run = 'Enter the first run date.';
    if (Object.keys(missing).length > 0) {
      setErrors(missing);
      return;
    }
    record.mutate({
      itemId,
      data: {
        location: values.location.trim(),
        url: values.url.trim() === '' ? null : values.url.trim(),
        first_run: values.first_run,
        last_run: lastRun,
        monitored: values.monitored,
      },
    });
  };

  return (
    <form
      className="app-form"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      {placement === undefined ? (
        <>
          <TextInput
            label="Where it runs"
            autoFocus
            value={values.location}
            onChange={(v) => {
              set('location', v);
            }}
            errorMessage={errors.location}
          />
          <TextInput
            label="Web address"
            type="url"
            description="Optional. Needed for daily checks."
            value={values.url}
            onChange={(v) => {
              set('url', v);
            }}
            errorMessage={errors.url}
          />
          <TextInput
            label="First run"
            type="date"
            value={values.first_run}
            onChange={(v) => {
              set('first_run', v);
            }}
            errorMessage={errors.first_run}
          />
        </>
      ) : (
        <p className="app-muted">{placement.location}</p>
      )}
      <TextInput
        label="Last run"
        type="date"
        description="Optional."
        value={values.last_run}
        onChange={(v) => {
          set('last_run', v);
        }}
        errorMessage={errors.last_run}
      />
      <CheckboxField
        isSelected={values.monitored}
        onChange={(v) => {
          set('monitored', v);
        }}
      >
        Check this page daily
      </CheckboxField>
      {formError !== null && (
        <p className="app-field-error" role="alert">
          {formError}
        </p>
      )}
      <div className="app-dialog-actions">
        <Button variant="ghost" onPress={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" isPending={record.isPending || update.isPending}>
          {placement === undefined ? 'Add placement' : 'Save'}
        </Button>
      </div>
    </form>
  );
}

/** "Add placement" (no `placement`) or "Edit" (prefilled) with the form in a dialog. */
export function PlacementFormButton({ itemId, placement }: { itemId: number; placement?: PlacementOut }) {
  const [open, setOpen] = useState(false);
  const editing = placement !== undefined;
  return (
    <>
      <Button
        size="sm"
        variant={editing ? 'ghost' : 'secondary'}
        icon={editing ? 'action.edit' : 'action.new'}
        onPress={() => {
          setOpen(true);
        }}
      >
        {editing ? 'Edit' : 'Add placement'}
      </Button>
      <ModalDialog title={editing ? 'Edit placement' : 'Add placement'} isOpen={open} onOpenChange={setOpen}>
        <PlacementForm
          itemId={itemId}
          placement={placement}
          onDone={() => {
            setOpen(false);
          }}
        />
      </ModalDialog>
    </>
  );
}

export function ConfirmTakedownButton({ itemId, placement }: { itemId: number; placement: PlacementOut }) {
  const [open, setOpen] = useState(false);
  const refresh = useRefreshPlacements(itemId);
  const confirm = useConfirmTakedown({
    mutation: {
      onSuccess: () => {
        refresh();
        setOpen(false);
        showToast({ title: 'Takedown confirmed' });
      },
      onError: (error) => {
        setOpen(false);
        showToast({
          title: "Couldn't confirm the takedown",
          description: apiErrorMessage(error),
          tone: 'error',
        });
      },
    },
  });
  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        icon="action.pull"
        onPress={() => {
          setOpen(true);
        }}
      >
        Confirm takedown
      </Button>
      <ModalDialog title="Confirm takedown?" role="alertdialog" isOpen={open} onOpenChange={setOpen}>
        <p>Confirms that {placement.location} no longer runs this content. This can’t be undone.</p>
        <div className="app-dialog-actions">
          <Button
            variant="ghost"
            onPress={() => {
              setOpen(false);
            }}
          >
            Cancel
          </Button>
          <Button
            variant="danger"
            icon="action.pull"
            isPending={confirm.isPending}
            onPress={() => {
              confirm.mutate({ placementId: placement.id });
            }}
          >
            Confirm takedown
          </Button>
        </div>
      </ModalDialog>
    </>
  );
}
