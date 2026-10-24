/*
 * Views: the built-ins (client constants; In queue has no tab, its stat opens it) and the viewer's saved views
 * (GET/POST/DELETE /views). The active view is derived from the URL; "Modified" appears when the filters or
 * sort have moved off it, and "Save view" stores the current filters, sort, and visible columns as a new view.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { SyntheticEvent } from 'react';
import {
  Dialog,
  DialogTrigger,
  Heading,
  Input,
  Popover,
  TextField,
  ToggleButton,
} from 'react-aria-components';

import {
  getListSavedViewsQueryKey,
  useCreateSavedView,
  useDeleteSavedView,
  useListSavedViews,
} from '../../api/generated/items/items';
import type { SavedViewOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { errorMessage } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import { IconButton } from '../../ui/IconButton';
import { showToast } from '../../ui/toast';
import {
  activeView,
  BUILT_IN_VIEWS,
  hasFilters,
  savedViewKey,
  savedViewToSearch,
  searchToSavedViewIn,
  viewSearch,
} from './search';
import type { QueueSearch } from './search';

const EMPTY_VIEWS: SavedViewOut[] = [];

export interface ViewBarProps {
  search: QueueSearch;
  /** Visible column ids, stored with a saved view. */
  columns: readonly string[];
  /** Open a view; `columns` is set when the view carries its own column choice. */
  onSelect: (search: QueueSearch, columns?: string[]) => void;
}

function SaveViewForm({
  search,
  columns,
  onSaved,
  close,
}: {
  search: QueueSearch;
  columns: readonly string[];
  onSaved: (view: SavedViewOut) => void;
  close: () => void;
}) {
  const [name, setName] = useState('');
  const create = useCreateSavedView();

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed === '') return;
    create.mutate(
      { data: searchToSavedViewIn(trimmed, search, columns) },
      {
        onSuccess: (view) => {
          onSaved(view);
          close();
        },
      },
    );
  };

  return (
    <form onSubmit={submit} className="flex w-64 flex-col gap-2">
      <Heading slot="title" className="text-ui font-medium">
        Save view
      </Heading>
      <TextField aria-label="View name" value={name} onChange={setName} maxLength={100} autoFocus>
        <Input className="app-input" placeholder="Name, e.g. Affiliate high risk" />
      </TextField>
      {create.isError && (
        <p role="alert" className="app-field-error">
          {errorMessage(create.error, "Couldn't save the view. Try again.")}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onPress={close}>
          Cancel
        </Button>
        <Button size="sm" variant="primary" type="submit" isDisabled={name.trim() === '' || create.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

export function ViewBar({ search, columns, onSelect }: ViewBarProps) {
  const qc = useQueryClient();
  const views = useListSavedViews();
  const saved = views.data ?? EMPTY_VIEWS;
  const active = activeView(search, saved);
  const del = useDeleteSavedView();
  const canSave = active.kind === 'custom' ? hasFilters(search) : active.modified;

  const isActive = (key: string) =>
    (active.kind === 'builtin' && active.id === key) ||
    (active.kind === 'saved' && savedViewKey(active.id) === key);

  const openSaved = (view: SavedViewOut) => {
    onSelect(savedViewToSearch(view), view.columns && view.columns.length > 0 ? view.columns : undefined);
  };

  return (
    <div className="app-view-group">
      <div className="app-view-tabs" role="group" aria-label="Views">
        {BUILT_IN_VIEWS.filter((view) => view.tab !== false).map((view) => (
          <ToggleButton
            key={view.id}
            className="app-view-tab"
            isSelected={isActive(view.id)}
            onChange={() => {
              onSelect(viewSearch(view.id), undefined);
            }}
          >
            {view.label}
          </ToggleButton>
        ))}
        {saved.length > 0 && <span className="app-view-sep" aria-hidden="true" />}
        {saved.map((view) => {
          const key = savedViewKey(view.id);
          return (
            <span key={view.id} className="app-view-saved">
              <ToggleButton
                className="app-view-tab"
                isSelected={isActive(key)}
                onChange={() => {
                  openSaved(view);
                }}
              >
                {view.name}
              </ToggleButton>
              {isActive(key) && (
                <IconButton
                  icon="action.close"
                  size="sm"
                  aria-label={`Delete view ${view.name}`}
                  isDisabled={del.isPending}
                  onPress={() => {
                    del.mutate(
                      { viewId: view.id },
                      {
                        onSuccess: () => {
                          void qc.invalidateQueries({ queryKey: getListSavedViewsQueryKey() });
                          showToast({ title: `Deleted view “${view.name}”` });
                          onSelect(viewSearch('mine'), undefined);
                        },
                        onError: (error) => {
                          showToast({
                            tone: 'error',
                            title: `Couldn't delete “${view.name}”`,
                            description: errorMessage(error, 'Try again.'),
                          });
                        },
                      },
                    );
                  }}
                />
              )}
            </span>
          );
        })}
      </div>
      <div className="app-view-actions">
        {active.kind !== 'custom' && active.modified && <span className="app-view-modified">Modified</span>}
        {canSave && (
          <DialogTrigger>
            <Button size="sm" variant="ghost" icon="action.save_view">
              Save view
            </Button>
            <Popover className="app-popover p-3" placement="bottom start" offset={4}>
              <Dialog aria-label="Save view" className="outline-none">
                {({ close }) => (
                  <SaveViewForm
                    search={search}
                    columns={columns}
                    close={close}
                    onSaved={(view) => {
                      void qc.invalidateQueries({ queryKey: getListSavedViewsQueryKey() });
                      showToast({ title: `Saved view “${view.name}”` });
                      openSaved(view);
                    }}
                  />
                )}
              </Dialog>
            </Popover>
          </DialogTrigger>
        )}
      </div>
    </div>
  );
}

/** Shown in the filter row (not after the tabs) so a failure never pushes the toolbar onto a second line. */
export function SavedViewsError() {
  const views = useListSavedViews();
  if (!views.isError) return null;
  return (
    <span className="app-inline-error" role="status">
      <Icon name="feedback.error" size={14} />
      <span>Couldn't load saved views.</span>
      <Button
        size="sm"
        variant="ghost"
        onPress={() => {
          void views.refetch();
        }}
      >
        Retry
      </Button>
    </span>
  );
}
