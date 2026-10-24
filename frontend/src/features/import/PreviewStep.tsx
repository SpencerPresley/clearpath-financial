/*
 * Step 3: what commit will do. Counts first, then every problem grouped by severity, each with its sheet row
 * number and the row's outcome (imported or skipped). Severity alone doesn't say that: the importer files some
 * skipped rows (duplicates, notes, already imported) as warnings or info. Commit skips error rows
 * (skip_rows_with_problems) and says how many before the admin presses it.
 */
import { Button as AriaButton, Disclosure, DisclosurePanel, Heading } from 'react-aria-components';

import type {
  ImportCountsOut,
  ImportJobOut,
  ImportPreviewOut,
  ImportPreviewRowOut,
  ImportProblemOut,
} from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import type { IconKey } from '../../ui/icons';
import { plural } from '../../ui/labels';
import { SEVERITY_GROUPS } from './labels';

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

function previewCounts(c: ImportCountsOut) {
  return [
    { label: 'Ready to import', value: c.ready },
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
}: {
  label: string;
  problems: readonly ImportProblemOut[];
  rows: readonly ImportPreviewRowOut[];
}) {
  const actions = new Map(rows.map((r) => [r.row_number, r.action]));
  const outcome = (row: number | null) => {
    if (row === null) return '—';
    const action = actions.get(row);
    if (action === undefined) return '—';
    return action === 'create' ? 'Imported' : 'Skipped';
  };
  return (
    <table className="app-table app-import-table" aria-label={label}>
      <colgroup>
        <col style={{ width: '4.5rem' }} />
        <col style={{ width: '13rem' }} />
        <col style={{ width: '12rem' }} />
        <col style={{ width: '6.5rem' }} />
        <col />
      </colgroup>
      <thead>
        <tr>
          {['Row', 'Column', 'Value', 'Outcome', 'What happens'].map((h) => (
            <th key={h} className="app-th" scope="col">
              <span className="app-th-label">{h}</span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {problems.map((p, i) => {
          const result = outcome(p.row_number);
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
                <span className="app-import-outcome" data-outcome={result}>
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

export function ProblemGroups({
  problems,
  rows,
  expandFirst = true,
}: {
  problems: readonly ImportProblemOut[];
  rows: readonly ImportPreviewRowOut[];
  expandFirst?: boolean;
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
              <span className="app-import-group-title">
                {g.title} · {g.problems.length}
              </span>
            </AriaButton>
          </Heading>
          <DisclosurePanel className="app-import-group-panel">
            <ProblemTable label={g.title} problems={g.problems} rows={rows} />
          </DisclosurePanel>
        </Disclosure>
      ))}
    </div>
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
  const unmapped = preview.unmapped.length;
  return (
    <div className="app-import-step">
      <header className="app-import-step-head">
        <h2 className="app-import-step-title">Preview</h2>
        <p className="app-import-step-detail">
          What importing does with each row. Imported rows become legacy items that keep their Request ID and
          history.
        </p>
      </header>
      {failed && job.error !== null && (
        <p className="app-import-banner" role="alert">
          <Icon name="feedback.error" size={16} />
          {job.error}
        </p>
      )}
      <Counts items={previewCounts(counts)} />
      <ProblemGroups problems={preview.problems} rows={preview.rows} />
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
    </div>
  );
}
