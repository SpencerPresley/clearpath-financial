/*
 * Export the approved view as it's filtered: xlsx, or a zip with an evidence pack per approved item. The job runs
 * in the background (spec §5.5: long operations show progress and leave the screen usable). Its one-line state
 * lives in the page's job store and shows on both tabs, ending in a download link or the reason it failed;
 * Retry re-sends the request that failed, not whatever the filters say now.
 */
import { Menu, MenuItem, MenuTrigger, Popover } from 'react-aria-components';

import { useCreateExport } from '../../api/generated/exports/exports';
import type { ExportIn } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { DownloadLink } from '../../ui/DownloadLink';
import { Icon } from '../../ui/Icon';
import { IconButton } from '../../ui/IconButton';
import { plural } from '../../ui/labels';
import { EXPORT_KEY } from './exportJobs';
import { exportBody } from './search';
import type { LibrarySearch } from './search';
import { useExportJob, useJobCallbacks } from './useExportJob';

function useStartExport() {
  const callbacks = useJobCallbacks();
  const create = useCreateExport({
    mutation: {
      onMutate: ({ data }) => {
        callbacks.starting(EXPORT_KEY, { request: data });
      },
      onSuccess: (job, { data }) => {
        callbacks.started(EXPORT_KEY, job, { request: data });
      },
      onError: (error, { data }) => {
        callbacks.refused(EXPORT_KEY, error, { request: data });
      },
    },
  });
  return (request: ExportIn) => {
    create.mutate({ data: request });
  };
}

/** The Export menu: the approved view only (precedent search can't be expressed as an export filter). */
export function ExportMenu({ search }: { search: LibrarySearch }) {
  const start = useStartExport();
  const { state } = useExportJob(EXPORT_KEY);
  const busy = state.kind === 'starting' || state.kind === 'running';
  return (
    <MenuTrigger>
      <Button size="sm" icon="action.export" isDisabled={busy}>
        Export
      </Button>
      <Popover className="app-popover" placement="bottom end" offset={4}>
        <Menu
          className="app-menu"
          aria-label="Export"
          onAction={(key) => {
            start(exportBody(search, key === 'packs'));
          }}
        >
          <MenuItem id="xlsx" textValue="Export view (.xlsx)" className="app-menu-item app-export-option">
            <span className="app-export-option-label">Export view (.xlsx)</span>
            <span className="app-export-option-hint">One row per item, in this order</span>
          </MenuItem>
          <MenuItem
            id="packs"
            textValue="Export view with evidence packs (.zip)"
            className="app-menu-item app-export-option"
          >
            <span className="app-export-option-label">Export view with evidence packs (.zip)</span>
            <span className="app-export-option-hint">Adds a pack per approved item, up to 200</span>
          </MenuItem>
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}

/** The export job's state, one line; rendered on both tabs so leaving the approved view doesn't lose it. */
export function ExportStatus() {
  const start = useStartExport();
  const callbacks = useJobCallbacks();
  const { state, record } = useExportJob(EXPORT_KEY);
  const dismiss = () => {
    callbacks.clear(EXPORT_KEY);
  };

  switch (state.kind) {
    case 'idle':
      return <span className="app-export-status" role="status" />;
    case 'starting':
    case 'running':
      return (
        <span className="app-export-status" role="status">
          <span className="app-export-progress" aria-hidden="true" />
          Building export…
        </span>
      );
    case 'ready':
      return (
        <span className="app-export-status" role="status">
          <span className="app-export-file" title={state.job.filename ?? undefined}>
            {state.job.filename ?? 'Export'}
          </span>
          {state.job.item_count !== null && (
            <span className="app-figure text-muted">{plural(state.job.item_count, 'item')}</span>
          )}
          <DownloadLink href={state.url} filename={state.job.filename}>
            Download
          </DownloadLink>
          <IconButton icon="action.close" size="sm" aria-label="Dismiss export" onPress={dismiss} />
        </span>
      );
    case 'refused':
    case 'failed':
    case 'lost':
      return (
        <span className="app-export-status app-export-error" role="alert">
          <Icon name="feedback.error" size={14} />
          <span className="app-export-message" title={state.message}>
            {state.message}
          </span>
          {record?.request !== undefined && (
            <Button
              size="sm"
              variant="ghost"
              onPress={() => {
                if (record.request !== undefined) start(record.request);
              }}
            >
              Retry export
            </Button>
          )}
          <IconButton icon="action.close" size="sm" aria-label="Dismiss export" onPress={dismiss} />
        </span>
      );
  }
}
