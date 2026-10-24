/*
 * Step 3: what commit will do. Counts first, then every problem grouped by severity (error: the row is skipped;
 * warning: imported with a note; info: read from a non-standard form), each with its sheet row number. Commit
 * skips error rows (skip_rows_with_problems), and says how many before the admin presses it.
 */
import { Button as AriaButton, Disclosure, DisclosurePanel, Heading } from 'react-aria-components';

import type {
  ImportCountsOut,
  ImportJobOut,
  ImportPreviewOut,
  ImportProblemOut,
} from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
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

function ProblemTable({ label, problems }: { label: string; problems: readonly ImportProblemOut[] }) {
  return (
    <table className="app-table app-import-table" aria-label={label}>
      <colgroup>
        <col style={{ width: '4.5rem' }} />
        <col style={{ width: '13rem' }} />
        <col style={{ width: '14rem' }} />
        <col />
      </colgroup>
      <thead>
        <tr>
          {['Row', 'Column', 'Value', 'What happens'].map((h) => (
            <th key={h} className="app-th" scope="col">
              <span className="app-th-label">{h}</span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {problems.map((p, i) => (
          <tr key={`${String(p.row_number)}-${p.kind}-${String(i)}`} className="app-tr">
            <td className="app-td app-figure">{p.row_number ?? 'Sheet'}</td>
            <td className="app-td" title={p.column ?? undefined}>
              {p.column ?? '—'}
            </td>
            <td className="app-td text-muted" title={p.value ?? undefined}>
              {p.value ?? '—'}
            </td>
            <td className="app-td app-import-message" title={p.message}>
              {p.message}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ProblemGroups({ problems }: { problems: readonly ImportProblemOut[] }) {
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
  const firstOpen = groups[0]?.severity;
  return (
    <div className="app-import-groups">
      {groups.map((g) => (
        <Disclosure
          key={g.severity}
          className="app-import-group"
          data-severity={g.severity}
          defaultExpanded={g.severity === 'error' || g.severity === firstOpen}
        >
          <Heading className="app-import-group-heading">
            <AriaButton slot="trigger" className="app-import-group-trigger">
              <Icon name="action.expand" size={14} className="app-import-group-caret" />
              <span className="app-import-group-title">
                {g.title} · {g.problems.length}
              </span>
              <span className="app-import-group-effect">{g.effect}</span>
            </AriaButton>
          </Heading>
          <DisclosurePanel className="app-import-group-panel">
            <ProblemTable label={g.title} problems={g.problems} />
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
}: {
  job: ImportJobOut;
  preview: ImportPreviewOut;
  committing: boolean;
  commitError: string | null;
  onCommit: () => void;
}) {
  const { counts } = preview;
  const failed = job.status === 'failed';
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
      <ProblemGroups problems={preview.problems} />
      <footer className="app-import-actions">
        <Button variant="primary" isDisabled={committing || counts.ready === 0} onPress={onCommit}>
          {committing
            ? 'Starting…'
            : failed
              ? 'Try the import again'
              : `Import ${plural(counts.ready, 'item')}`}
        </Button>
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
