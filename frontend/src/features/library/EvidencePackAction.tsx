/*
 * Per-item evidence pack (the item's latest approved version, its decision record, terms snapshot, evidence
 * hashes): POST /items/{id}/evidence-pack starts a job, the page's job store keeps it (so a row that's filtered
 * away and back, or a tab switch, finds it still running or ready), and a download link replaces the button.
 * Legacy items have no decision record (ledger ruling), so they say so instead of offering a button that can
 * only be refused; any other refusal (409) shows the server's reason in place of the button.
 */
import { Button as AriaButton } from 'react-aria-components';

import { useCreateEvidencePack } from '../../api/generated/exports/exports';
import { Button } from '../../ui/Button';
import { DownloadLink } from '../../ui/DownloadLink';
import { Icon } from '../../ui/Icon';
import { Tooltip } from '../../ui/Tooltip';
import { packKey } from './exportJobs';
import { useExportJob, useJobCallbacks } from './useExportJob';

/** The server's 409 sentence for a legacy item (exports.evidence.latest_approval), so the two never disagree. */
export function legacyPackReason(itemKey: string): string {
  return `${itemKey} is a legacy import with no decision record; its approval is in the tracker history.`;
}

/**
 * Why there's no pack. In a dense table cell (`compact`) a short label plus an info button whose tooltip holds
 * the whole sentence; elsewhere the sentence itself. Screen readers get the sentence either way.
 */
function Reason({
  short,
  message,
  itemKey,
  compact,
}: {
  short: string;
  message: string;
  itemKey: string;
  compact: boolean;
}) {
  if (!compact) return <span className="app-pack-note app-pack-wrap">{message}</span>;
  return (
    <span className="app-pack-reason">
      <span className="app-pack-note" aria-hidden="true">
        {short}
      </span>
      <Tooltip content={message} delay={200}>
        <AriaButton className="app-pack-why" aria-label={`Why there's no evidence pack for ${itemKey}`}>
          <Icon name="feedback.info" size={14} />
        </AriaButton>
      </Tooltip>
      <span className="sr-only">{message}</span>
    </span>
  );
}

export function EvidencePackAction({
  itemId,
  itemKey,
  isLegacy,
  compact = false,
}: {
  itemId: number;
  itemKey: string;
  isLegacy: boolean;
  /** A table cell: short labels, reasons in a tooltip. */
  compact?: boolean;
}) {
  const key = packKey(itemId);
  const callbacks = useJobCallbacks();
  const create = useCreateEvidencePack({
    mutation: {
      onMutate: ({ itemId: id }) => {
        callbacks.starting(packKey(id));
      },
      onSuccess: (job, { itemId: id }) => {
        callbacks.started(packKey(id), job);
      },
      onError: (error, { itemId: id }) => {
        callbacks.refused(packKey(id), error);
      },
    },
  });
  const { state } = useExportJob(key);

  if (isLegacy) {
    return <Reason short="No pack" message={legacyPackReason(itemKey)} itemKey={itemKey} compact={compact} />;
  }

  const start = () => {
    create.mutate({ itemId });
  };
  // The label names the item, not a version: the pack records the item's latest approval.
  const label = compact ? 'Build pack' : 'Build item pack';

  switch (state.kind) {
    case 'idle':
      return (
        <Button
          size="sm"
          variant="ghost"
          icon="action.export"
          aria-label={`${label} for ${itemKey}`}
          onPress={start}
        >
          {label}
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
        return <Reason short="No pack" message={state.message} itemKey={itemKey} compact={compact} />;
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
