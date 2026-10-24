/*
 * Step 3: what commit will do. Counts first, then every problem grouped by severity, each with its sheet row
 * number and its outcome: how an imported row was adjusted ("Imported, date from last round"), or why the row
 * is skipped. Severity alone doesn't say that: the importer files some skipped rows (duplicates, notes) as
 * warnings or info. Commit skips error rows (skip_rows_with_problems) and says how many before the admin presses it.
 *
 * Rows already in the app collapse into one line naming the import they came from: after a seed that's every
 * row, and their notes belong to that import, whose read-only preview shows what each became. A committed job's
 * preview is that record: what commit did, with no commit button.
 */
import { Link } from '@tanstack/react-router';
import { Button as AriaButton, Disclosure, DisclosurePanel, Heading } from 'react-aria-components';

import type {
  ImportCountsOut,
  ImportJobOut,
  ImportPreviewOut,
  ImportPreviewRowOut,
  ImportProblemOut,
} from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { ButtonLink } from '../../ui/ButtonLink';
import { Icon } from '../../ui/Icon';
import type { IconKey } from '../../ui/icons';
import { formatDate, plural } from '../../ui/labels';
import { problemOutcome, SEVERITY_GROUPS } from './labels';

export function Counts({ items }: { items: readonly { label: string; value: number; tone?: 'error' }[] }) {
  return (
    <dl className="app-import-counts">
      {items.map((item) => (
        <div key={item.label} className="app-import-count" data-tone={item.tone}>
          <dt className="app-import-count-label">{item.label}</dt>
          <dd className="app-import-count-figure">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function previewCounts(c: ImportCountsOut, committed: boolean) {
  return [
    { label: committed ? 'Items created' : 'Ready to import', value: c.ready },
    { label: 'Blocked by errors', value: c.blocked, tone: c.blocked > 0 ? ('error' as const) : undefined },
    { label: 'Duplicates', value: c.duplicates },
    { label: 'Already imported', value: c.already_imported },
    { label: 'Not tracker rows', value: c.not_data },
    { label: 'Rows in the sheet', value: c.rows_total },
  ];
}

export function ProblemTable({
  label,
  problems,
  rows,
  committed = false,
}: {
  label: string;
  problems: readonly ImportProblemOut[];
  rows: readonly ImportPreviewRowOut[];
  /** Past tense: what commit did. */
  committed?: boolean;
}) {
  const actions = new Map(rows.map((r) => [r.row_number, r.action]));
  return (
    <table className="app-table app-import-table" aria-label={label}>
      <colgroup>
        <col style={{ width: '4.5rem' }} />
        <col style={{ width: '12rem' }} />
        <col style={{ width: '11rem' }} />
        <col style={{ width: '14rem' }} />
        <col />
      </colgroup>
      <thead>
        <tr>
          {['Row', 'Column', 'Value', 'Outcome', committed ? 'What happened' : 'What happens'].map((h) => (
            <th key={h} className="app-th" scope="col">
              <span className="app-th-label">{h}</span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {problems.map((p, i) => {
          const action = p.row_number === null ? undefined : actions.get(p.row_number);
          const result = problemOutcome(p.kind, action, committed);
          return (
            <tr key={`${String(p.row_number)}-${p.kind}-${String(i)}`} className="app-tr">
              <td className="app-td app-figure">{p.row_number ?? 'Sheet'}</td>
              <td className="app-td" title={p.column ?? undefined}>
                {p.column ?? '—'}
              </td>
              <td className="app-td text-muted" title={p.value ?? undefined}>
                {p.value ?? '—'}
              </td>
              <td className="app-td">
                <span
                  className="app-import-outcome"
                  data-skipped={action !== undefined && action !== 'create' ? 'true' : undefined}
                >
                  {result}
                </span>
              </td>
              <td className="app-td app-import-message">{p.message}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const GROUP_ICON: Record<ImportProblemOut['severity'], IconKey> = {
  error: 'feedback.error',
  warning: 'severity.warning',
  info: 'feedback.info',
};

/**
 * "Errors · 2", or "Errors · 6 in 5 rows" when a row has more than one problem, so the header agrees with the
 * row counts ("5 rows with errors are skipped"). The table lists every problem, so every affected row appears.
 */
function groupTitle(title: string, problems: readonly ImportProblemOut[]): string {
  const rows = new Set(problems.flatMap((p) => (p.row_number === null ? [] : [p.row_number]))).size;
  const n = String(problems.length);
  return rows > 0 && rows < problems.length ? `${title} · ${n} in ${plural(rows, 'row')}` : `${title} · ${n}`;
}

export function ProblemGroups({
  problems,
  rows,
  expandFirst = true,
  committed = false,
}: {
  problems: readonly ImportProblemOut[];
  rows: readonly ImportPreviewRowOut[];
  expandFirst?: boolean;
  committed?: boolean;
}) {
  const groups = SEVERITY_GROUPS.map((g) => ({
    ...g,
    problems: problems
      .filter((p) => p.severity === g.severity)
      .sort((a, b) => (a.row_number ?? 0) - (b.row_number ?? 0)),
  })).filter((g) => g.problems.length > 0);
  if (groups.length === 0) {
    return (
      <p className="app-import-empty">
        <Icon name="feedback.info" size={16} />
        No problems: every row reads cleanly.
      </p>
    );
  }
  const firstOpen = expandFirst ? groups[0]?.severity : undefined;
  return (
    <div className="app-import-groups">
      {groups.map((g) => (
        <Disclosure
          key={g.severity}
          className="app-import-group"
          data-severity={g.severity}
          defaultExpanded={expandFirst && (g.severity === 'error' || g.severity === firstOpen)}
        >
          <Heading className="app-import-group-heading">
            <AriaButton slot="trigger" className="app-import-group-trigger">
              <Icon name="action.expand" size={14} className="app-import-group-caret" />
              <Icon name={GROUP_ICON[g.severity]} size={16} className="app-import-group-icon" />
              <span className="app-import-group-title">{groupTitle(g.title, g.problems)}</span>
            </AriaButton>
          </Heading>
          <DisclosurePanel className="app-import-group-panel">
            <ProblemTable label={g.title} problems={g.problems} rows={rows} committed={committed} />
          </DisclosurePanel>
        </Disclosure>
      ))}
    </div>
  );
}

/** "178 rows already imported from this tracker", with the import they came from when there's one. */
function AlreadyImported({ preview, withLink }: { preview: ImportPreviewOut; withLink: boolean }) {
  const n = preview.counts.already_imported;
  const source = preview.already_imported_from;
  return (
    <p className="app-import-info-line" role="status">
      <Icon name="feedback.info" size={16} className="app-import-info-icon" />
      <span>
        {plural(n, 'row')} already imported from this tracker
        {source?.committed_at != null && ` on ${formatDate(source.committed_at)}`}
        {source !== null && (
          <>
            {' '}
            (<span className="app-import-file">{source.filename}</span>)
          </>
        )}
        . {n === 1 ? 'It isn’t' : 'They aren’t'} imported again.
      </span>
      {withLink && source !== null && (
        <Link
          to="/import"
          search={{ job: source.job_id, step: 'preview' }}
          className="app-library-link app-import-info-link"
        >
          See how each row was imported
        </Link>
      )}
    </p>
  );
}

export function PreviewStep({
  job,
  preview,
  committing,
  commitError,
  onCommit,
  onMapValues,
}: {
  job: ImportJobOut;
  preview: ImportPreviewOut;
  committing: boolean;
  commitError: string | null;
  onCommit: () => void;
  /** Back to the Values step; offered while values are unmapped (their rows are skipped otherwise). */
  onMapValues: () => void;
}) {
  const { counts } = preview;
  const failed = job.status === 'failed';
  const committed = job.status === 'committed';
  const unmapped = preview.unmapped.length;
  const already = new Set(
    preview.rows.filter((r) => r.action === 'skip_already_imported').map((r) => r.row_number),
  );
  const problems = preview.problems.filter((p) => p.row_number === null || !already.has(p.row_number));
  // Everything is already in (the sample after a seed): no disabled Import button, the next step is the import
  // that brought the rows in.
  const source = preview.already_imported_from;
  const nothingNew =
    counts.ready === 0 && counts.already_imported > 0 && counts.blocked === 0 && unmapped === 0 && !failed;
  return (
    <div className="app-import-step">
      <header className="app-import-step-head">
        <h2 className="app-import-step-title">Preview</h2>
        <p className="app-import-step-detail">
          {committed
            ? `What the import did with each row${job.committed_at === null ? '' : ` on ${formatDate(job.committed_at)}`}. Imported rows became legacy items that keep their Request ID and history.`
            : 'What importing does with each row. Imported rows become legacy items that keep their Request ID and history.'}
        </p>
      </header>
      {failed && job.error !== null && (
        <p className="app-import-banner" role="alert">
          <Icon name="feedback.error" size={16} />
          {job.error}
        </p>
      )}
      <Counts items={previewCounts(counts, committed)} />
      {counts.already_imported > 0 && !committed && (
        <AlreadyImported preview={preview} withLink={!nothingNew} />
      )}
      <ProblemGroups problems={problems} rows={preview.rows} committed={committed} />
      {!committed && nothingNew && (
        <footer className="app-import-actions">
          {source !== null && (
            <ButtonLink to="/import" search={{ job: source.job_id, step: 'preview' }} variant="primary">
              See how each row was imported
            </ButtonLink>
          )}
          <p className="app-import-note">Nothing new to import.</p>
        </footer>
      )}
      {!committed && !nothingNew && (
        <footer className="app-import-actions">
          <Button variant="primary" isDisabled={committing || counts.ready === 0} onPress={onCommit}>
            {committing
              ? 'Starting…'
              : failed
                ? 'Try the import again'
                : `Import ${plural(counts.ready, 'item')}`}
          </Button>
          {unmapped > 0 && <Button onPress={onMapValues}>Map {plural(unmapped, 'value')}</Button>}
          {commitError !== null ? (
            <p className="app-import-error-text" role="alert">
              <Icon name="feedback.error" size={14} />
              {commitError}
            </p>
          ) : counts.ready === 0 ? (
            <p className="app-import-note">Nothing to import: fix the mapping or the sheet first.</p>
          ) : (
            counts.blocked > 0 && (
              <p className="app-import-note">
                {plural(counts.blocked, 'row')} with errors {counts.blocked === 1 ? 'is' : 'are'} skipped.
              </p>
            )
          )}
        </footer>
      )}
    </div>
  );
}
