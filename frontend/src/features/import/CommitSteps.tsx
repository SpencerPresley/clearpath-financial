/*
 * Steps 4 and 5: the commit job's progress (it runs in the background, so the admin can leave), and the summary
 * of what it created, with a link to every imported item, then what it skipped and warned about (collapsed).
 */
import { Link } from '@tanstack/react-router';
import type { ReactNode } from 'react';
import { Button as AriaButton, Disclosure, DisclosurePanel, Heading } from 'react-aria-components';

import type {
  ImportJobOut,
  ImportPreviewOut,
  ImportPreviewRowOut,
  RowAction,
} from '../../api/generated/model';
import { StatusBadge } from '../../ui/badges';
import { ButtonLink } from '../../ui/ButtonLink';
import { Icon } from '../../ui/Icon';
import type { IconKey } from '../../ui/icons';
import { formatDate, plural } from '../../ui/labels';
import { SkeletonTable } from '../../ui/Skeleton';
import { Counts, ProblemTable } from './PreviewStep';

const SKIP_REASON: Record<Exclude<RowAction, 'create'>, string> = {
  blocked: 'Had errors',
  skip_duplicate: 'Duplicate of an earlier row',
  skip_already_imported: 'Already imported',
  skip_not_data: 'Not a tracker row',
};

function SummarySection({
  title,
  count,
  icon,
  children,
}: {
  title: string;
  count: number;
  icon: IconKey;
  children: ReactNode;
}) {
  return (
    <Disclosure className="app-import-group">
      <Heading className="app-import-group-heading">
        <AriaButton slot="trigger" className="app-import-group-trigger">
          <Icon name="action.expand" size={14} className="app-import-group-caret" />
          <Icon name={icon} size={16} className="app-import-group-icon" />
          <span className="app-import-group-title">
            {title} ({count})
          </span>
        </AriaButton>
      </Heading>
      <DisclosurePanel className="app-import-group-panel">{children}</DisclosurePanel>
    </Disclosure>
  );
}

function SkippedTable({ rows }: { rows: readonly ImportPreviewRowOut[] }) {
  return (
    <table className="app-table app-import-table" aria-label="Skipped rows">
      <colgroup>
        <col style={{ width: '4.5rem' }} />
        <col style={{ width: '9rem' }} />
        <col />
        <col style={{ width: '16rem' }} />
      </colgroup>
      <thead>
        <tr>
          {['Row', 'Request ID', 'Title', 'Why'].map((h) => (
            <th key={h} className="app-th" scope="col">
              <span className="app-th-label">{h}</span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.row_number} className="app-tr">
            <td className="app-td app-figure">{row.row_number}</td>
            <td className="app-td app-import-ref">{row.legacy_ref ?? '—'}</td>
            <td className="app-td" title={row.title ?? undefined}>
              {row.title ?? '—'}
            </td>
            <td className="app-td">{row.action === 'create' ? '—' : SKIP_REASON[row.action]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function CommitProgress({ ready }: { ready: number | undefined }) {
  return (
    <div className="app-import-step">
      <header className="app-import-step-head">
        <h2 className="app-import-step-title">Importing</h2>
      </header>
      <div className="app-import-progress-panel" role="status">
        <div className="app-import-progress" aria-hidden="true" />
        <p className="app-import-progress-text">
          {ready === undefined ? 'Importing items…' : `Importing ${plural(ready, 'item')}…`}
        </p>
        <p className="app-import-step-detail">
          This runs in the background. You can leave this page; Recent imports shows how it ended.
        </p>
      </div>
    </div>
  );
}

const ITEM_COLUMNS = ['9rem', '1fr', '11rem', '8rem'] as const;

export function ImportSummary({
  job,
  preview,
}: {
  job: ImportJobOut;
  preview: ImportPreviewOut | undefined;
}) {
  const summary = job.summary;
  // Until the refetched preview arrives, the cached one is from before commit and has no item ids.
  const committed = preview?.status === 'committed' ? preview : undefined;
  const rows = committed?.rows ?? [];
  const created = rows.filter((r) => r.action === 'create' && r.item_id !== null);
  const skipped = rows.filter((r) => r.action !== 'create');
  const warnings = (committed?.problems ?? []).filter((p) => p.severity === 'warning');
  // The library's approved view shows current status approved, legacy included: these rows land there.
  const approved = created.filter((r) => r.status === 'approved').length;
  return (
    <div className="app-import-step">
      <header className="app-import-step-head app-import-summary-head">
        <div>
          <h2 className="app-import-step-title">
            {summary === null ? 'Imported' : `Imported ${plural(summary.created, 'item')}`}
          </h2>
          <p className="app-import-step-detail">
            {job.committed_at === null ? null : `${formatDate(job.committed_at)} · `}Legacy items keep their
            Request ID and tracker history, and count toward metrics.
          </p>
        </div>
        {committed !== undefined && approved > 0 && (
          <ButtonLink to="/library" search={{ legacy: 'only' }} size="sm" icon="nav.library">
            Approved legacy items ({approved})
          </ButtonLink>
        )}
      </header>
      {summary !== null && (
        <Counts
          items={[
            { label: 'Items created', value: summary.created },
            { label: 'Rows skipped', value: summary.skipped },
            { label: 'Partners created', value: summary.partners_created },
          ]}
        />
      )}
      <div className="app-import-panel">
        {committed === undefined ? (
          <SkeletonTable rows={6} columns={ITEM_COLUMNS.map((w) => w)} label="Loading the imported items" />
        ) : (
          <table className="app-table app-import-table" aria-label="Imported items">
            <colgroup>
              {ITEM_COLUMNS.map((w, i) => (
                <col key={i} style={w === '1fr' ? undefined : { width: w }} />
              ))}
            </colgroup>
            <thead>
              <tr>
                {['Request ID', 'Title', 'Status', 'Submitted'].map((h) => (
                  <th key={h} className="app-th" scope="col">
                    <span className="app-th-label">{h}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {created.map((row) => (
                <tr key={row.row_number} className="app-tr">
                  <td className="app-td app-import-ref">{row.legacy_ref}</td>
                  <td className="app-td">
                    <Link
                      to="/items/$itemId"
                      params={{ itemId: String(row.item_id) }}
                      className="app-library-link"
                    >
                      {row.title ?? row.legacy_ref ?? `Row ${String(row.row_number)}`}
                    </Link>
                  </td>
                  <td className="app-td">{row.status !== null && <StatusBadge status={row.status} />}</td>
                  <td className="app-td app-figure">
                    {row.submitted_on === null ? '—' : formatDate(row.submitted_on)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {committed !== undefined && (skipped.length > 0 || warnings.length > 0) && (
        <div className="app-import-groups">
          {skipped.length > 0 && (
            <SummarySection title="Skipped" count={skipped.length} icon="feedback.error">
              <SkippedTable rows={skipped} />
            </SummarySection>
          )}
          {warnings.length > 0 && (
            <SummarySection title="Warnings" count={warnings.length} icon="severity.warning">
              <ProblemTable label="Warnings" problems={warnings} rows={rows} committed />
            </SummarySection>
          )}
        </div>
      )}
    </div>
  );
}
