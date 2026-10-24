/*
 * Export the approved view as it's filtered: xlsx, or a zip with an evidence pack per approved item. The job runs
 * in the background (spec §5.5: long operations show progress and leave the screen usable); its state sits
 * beside the button in one line, ending in a download link or the reason it failed.
 */
import { Menu, MenuItem, MenuTrigger, Popover } from 'react-aria-components';

import { useCreateExport } from '../../api/generated/exports/exports';
import { Button } from '../../ui/Button';
import { DownloadLink } from '../../ui/DownloadLink';
import { Icon } from '../../ui/Icon';
import { IconButton } from '../../ui/IconButton';
import { plural } from '../../ui/labels';
import { exportBody } from './search';
import type { LibrarySearch } from './search';
import { useExportJob } from './useExportJob';
import type { ExportJobState } from './useExportJob';

export function ExportControl({ search }: { search: LibrarySearch }) {
  const create = useCreateExport();
  const job = useExportJob(create);
  const lastPacks = create.variables?.data.include_evidence_packs ?? false;

  const start = (packs: boolean) => {
    job.reset();
    create.mutate({ data: exportBody(search, packs) }, { onSuccess: job.track });
  };
  const busy = job.state.kind === 'starting' || job.state.kind === 'running';

  return (
    <div className="app-export">
      <ExportStatus
        state={job.state}
        onRetry={() => {
          start(lastPacks);
        }}
        onDismiss={() => {
          job.reset();
          create.reset();
        }}
      />
      <MenuTrigger>
        <Button size="sm" icon="action.export" isDisabled={busy}>
          Export
        </Button>
        <Popover className="app-popover" placement="bottom end" offset={4}>
          <Menu
            className="app-menu"
            aria-label="Export"
            onAction={(key) => {
              start(key === 'packs');
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
    </div>
  );
}

function ExportStatus({
  state,
  onRetry,
  onDismiss,
}: {
  state: ExportJobState;
  onRetry: () => void;
  onDismiss: () => void;
}) {
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
          <IconButton icon="action.close" size="sm" aria-label="Dismiss export" onPress={onDismiss} />
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
          <Button size="sm" variant="ghost" onPress={onRetry}>
            Retry export
          </Button>
          <IconButton icon="action.close" size="sm" aria-label="Dismiss export" onPress={onDismiss} />
        </span>
      );
  }
}
