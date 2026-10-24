/*
 * Start an import: upload a tracker xlsx or load the bundled sample, then pick up where any recent import left
 * off. Both starts land on the new job's first step.
 */
import { useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { FileTrigger } from 'react-aria-components';

import {
  getGetImportQueryKey,
  getListImportsQueryKey,
  useListImports,
  useLoadSampleImport,
  useUploadImport,
} from '../../api/generated/imports/imports';
import type { ImportJobOut, ImportJobSummaryOut } from '../../api/generated/model';
import { Badge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { errorMessage } from '../../ui/errorMessage';
import { fieldErrorsFrom } from '../../ui/forms/apiErrors';
import { Icon } from '../../ui/Icon';
import { formatDate } from '../../ui/labels';
import { SkeletonTable } from '../../ui/Skeleton';
import { IMPORT_STATUS_META } from './labels';

const XLSX = ['.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'];
const RECENT_COLUMNS = ['16rem', '7rem', '5rem', '9rem', '8rem', '1fr'] as const;

function ImportStatusBadge({ status }: { status: ImportJobSummaryOut['status'] }) {
  return <Badge meta={IMPORT_STATUS_META[status]} />;
}

function outcome(job: ImportJobSummaryOut): string {
  if (job.summary !== null)
    return `${String(job.summary.created)} created · ${String(job.summary.skipped)} skipped`;
  if (job.error !== null) return job.error;
  if (job.status === 'committing') return 'Importing…';
  return 'Not imported yet';
}

/** While any listed import is committing, poll so its row turns Imported or Failed without a reload. */
export const RECENT_POLL_MS = 2000;

function RecentImports() {
  const recent = useListImports({
    query: {
      refetchInterval: (q) =>
        (q.state.data ?? []).some((job) => job.status === 'committing') ? RECENT_POLL_MS : false,
    },
  });
  if (recent.isPending) {
    return <SkeletonTable rows={3} columns={RECENT_COLUMNS.map((w) => w)} label="Loading recent imports" />;
  }
  if (recent.isError) {
    return (
      <div className="app-import-inline-error" role="alert">
        <Icon name="feedback.error" size={14} />
        <span>{errorMessage(recent.error, "Couldn't load recent imports.")}</span>
        <Button
          size="sm"
          variant="ghost"
          onPress={() => {
            void recent.refetch();
          }}
        >
          Retry
        </Button>
      </div>
    );
  }
  if (recent.data.length === 0) {
    return (
      <EmptyState icon="nav.import" title="No imports yet">
        Start with the sample tracker to see how a tracker maps onto items.
      </EmptyState>
    );
  }
  return (
    <table className="app-table app-import-table" aria-label="Recent imports">
      <colgroup>
        {RECENT_COLUMNS.map((w, i) => (
          <col key={i} style={w === '1fr' ? undefined : { width: w }} />
        ))}
      </colgroup>
      <thead>
        <tr>
          {['File', 'Status', 'Rows', 'By', 'Started', 'Result'].map((h) => (
            <th key={h} className="app-th" scope="col">
              <span className="app-th-label">{h}</span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {recent.data.map((job) => (
          <tr key={job.id} className="app-tr">
            <td className="app-td">
              <Link to="/import" search={{ job: job.id }} className="app-library-link">
                {job.filename}
              </Link>
            </td>
            <td className="app-td">
              <ImportStatusBadge status={job.status} />
            </td>
            <td className="app-td app-figure">{job.row_count}</td>
            <td className="app-td">{job.created_by.name}</td>
            <td className="app-td app-figure">{formatDate(job.created_at)}</td>
            <td className="app-td" title={outcome(job)}>
              <span
                className="app-import-result"
                data-failed={job.error !== null && job.summary === null ? 'true' : undefined}
              >
                {outcome(job)}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ImportStart({ onStarted }: { onStarted: (jobId: number) => void }) {
  const queryClient = useQueryClient();
  const started = (job: ImportJobOut) => {
    queryClient.setQueryData(getGetImportQueryKey(job.id), job);
    void queryClient.invalidateQueries({ queryKey: getListImportsQueryKey() });
    onStarted(job.id);
  };
  const upload = useUploadImport({ mutation: { onSuccess: started } });
  const sample = useLoadSampleImport({ mutation: { onSuccess: started } });
  const uploadError = upload.isError ? fieldErrorsFrom(upload.error, ['file']) : null;
  const busy = upload.isPending || sample.isPending;

  return (
    <div className="app-import-start">
      <section className="app-import-sources" aria-label="Start an import">
        <div className="app-import-source">
          <h2 className="app-import-source-title">Upload a tracker</h2>
          <p className="app-import-source-detail">
            An .xlsx with one row per request, up to 5 MB. You map its columns next.
          </p>
          <div className="app-import-source-action">
            <FileTrigger
              acceptedFileTypes={XLSX}
              onSelect={(files) => {
                const file = files?.[0];
                if (file !== undefined) upload.mutate({ data: { file } });
              }}
            >
              <Button variant="primary" icon="action.import" isDisabled={busy}>
                {upload.isPending ? 'Uploading…' : 'Upload tracker (.xlsx)'}
              </Button>
            </FileTrigger>
            {upload.isPending && upload.variables.data.file instanceof File && (
              <span className="app-import-file">{upload.variables.data.file.name}</span>
            )}
          </div>
          {uploadError !== null && (
            <p className="app-field-error" role="alert">
              {uploadError.fields.file ?? uploadError.form}
            </p>
          )}
        </div>
        <div className="app-import-source">
          <h2 className="app-import-source-title">Try the sample</h2>
          <p className="app-import-source-detail">
            The team&apos;s 2025–26 review tracker, with the tracker&apos;s known inconsistencies.
          </p>
          <div className="app-import-source-action">
            <Button
              isDisabled={busy}
              onPress={() => {
                sample.mutate();
              }}
            >
              {sample.isPending ? 'Loading…' : 'Load sample tracker'}
            </Button>
          </div>
          {sample.isError && (
            <p className="app-field-error" role="alert">
              {errorMessage(sample.error, "Couldn't load the sample. Try again.")}
            </p>
          )}
        </div>
      </section>
      <section className="app-import-recent" aria-labelledby="recent-imports">
        <h2 id="recent-imports" className="app-import-section-title">
          Recent imports
        </h2>
        <div className="app-import-panel">
          <RecentImports />
        </div>
      </section>
    </div>
  );
}
