/*
 * Per-item evidence pack (approved version, decision record, terms snapshot, evidence hashes): POST
 * /items/{id}/evidence-pack starts a job, the row polls it, and a download link replaces the button. Legacy
 * items have no decision record (ledger ruling), so they say so instead of offering a button that can only be
 * refused; any other refusal (409) shows the server's reason in place of the button.
 */
import { useCreateEvidencePack } from '../../api/generated/exports/exports';
import { Button } from '../../ui/Button';
import { DownloadLink } from '../../ui/DownloadLink';
import { useExportJob } from './useExportJob';

export const LEGACY_PACK_REASON =
  'Imported from the tracker: there is no decision record to pack. The approval is in the tracker history.';

export function EvidencePackAction({
  itemId,
  itemKey,
  isLegacy,
}: {
  itemId: number;
  itemKey: string;
  isLegacy: boolean;
}) {
  const create = useCreateEvidencePack();
  const job = useExportJob(create);

  if (isLegacy) {
    return (
      <span className="app-pack-note" title={LEGACY_PACK_REASON}>
        <span>No pack · legacy</span>
        <span className="sr-only">{LEGACY_PACK_REASON}</span>
      </span>
    );
  }

  const start = () => {
    job.reset();
    create.mutate({ itemId }, { onSuccess: job.track });
  };
  const { state } = job;

  switch (state.kind) {
    case 'idle':
      return (
        <Button
          size="sm"
          variant="ghost"
          icon="action.export"
          aria-label={`Evidence pack for ${itemKey}`}
          onPress={start}
        >
          Evidence pack
        </Button>
      );
    case 'starting':
    case 'running':
      return (
        <span className="app-pack-note" role="status">
          Building pack…
        </span>
      );
    case 'ready':
      return (
        <DownloadLink
          href={state.url}
          filename={state.job.filename}
          aria-label={`Download evidence pack for ${itemKey}`}
        >
          Download
        </DownloadLink>
      );
    case 'refused':
      // 409: nothing to pack (never approved, or legacy). The reason replaces the button: retrying can't help.
      if (state.status === 409) {
        return (
          <span className="app-pack-note" title={state.message}>
            {state.message}
          </span>
        );
      }
      return <PackError message={state.message} itemKey={itemKey} onRetry={start} />;
    case 'failed':
    case 'lost':
      return <PackError message={state.message} itemKey={itemKey} onRetry={start} />;
  }
}

function PackError({ message, itemKey, onRetry }: { message: string; itemKey: string; onRetry: () => void }) {
  return (
    <span className="app-pack-error" role="alert">
      <span className="truncate" title={message}>
        {message}
      </span>
      <Button size="sm" variant="ghost" aria-label={`Retry evidence pack for ${itemKey}`} onPress={onRetry}>
        Retry
      </Button>
    </span>
  );
}
