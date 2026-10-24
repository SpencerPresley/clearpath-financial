import { useId } from 'react';

import type { LiveChecks } from '../copy/useLiveChecks';
import { plural } from '../labels';
import { FindingSummary } from './FindingSummary';
import { groupFindings } from './groupFindings';

export interface LiveFindingsProps {
  checks: LiveChecks;
  /** Shown while idle (no request): why nothing is checked yet. */
  idleMessage?: string;
  className?: string;
}

/**
 * The live code-check results beside a copy editor (spec §4.3 Intake). Previews are code checks only, so
 * the panel says so and says when the AI review happens. Previous results stay up while a newer text is
 * being checked, so the list doesn't flash empty on every keystroke.
 */
export function LiveFindings({
  checks,
  idleMessage = 'Checks run as you type.',
  className,
}: LiveFindingsProps) {
  const titleId = useId();
  const { status, findings } = checks;
  const hasResult = checks.checkedText !== null && status !== 'idle';
  const groups = groupFindings(
    findings.map((finding, index) => ({ ...finding, state: 'open' as const, index })),
  );
  const blocking = findings.filter((finding) => finding.severity === 'blocking').length;

  let body: React.ReactNode;
  if (status === 'idle') {
    body = <p className="app-live-empty">{idleMessage}</p>;
  } else if (status === 'error') {
    body = <p className="app-live-empty">Live checks unavailable. They run again when you submit.</p>;
  } else if (!hasResult) {
    body = <p className="app-live-empty">Checking…</p>;
  } else if (findings.length === 0) {
    body = <p className="app-live-empty">No code findings.</p>;
  } else {
    body = groups.map((group) => (
      <section key={group.id} className="app-live-group" aria-label={group.label}>
        <h3 className="app-live-group-label">
          {group.label} <span className="app-figure">{group.findings.length}</span>
        </h3>
        <ul className="app-live-list">
          {group.findings.map((finding) => (
            <li key={`${finding.rule_id}-${String(finding.index)}`} className="app-live-item">
              <FindingSummary
                severity={finding.severity}
                source={finding.source}
                message={finding.message}
                citation={finding.citation}
                quote={finding.quote}
                suggestedFix={finding.suggested_fix}
              />
            </li>
          ))}
        </ul>
      </section>
    ));
  }

  return (
    <section aria-labelledby={titleId} className={className} data-status={status}>
      <div className="app-live-head">
        <h2 id={titleId} className="app-live-title">
          Code checks
        </h2>
        {hasResult && findings.length > 0 && (
          <span className="app-live-count">
            {plural(findings.length, 'finding')}
            {blocking > 0 && ` · ${String(blocking)} blocking`}
          </span>
        )}
        <span className="app-live-status" role="status">
          {status === 'checking' && hasResult ? 'Checking…' : ''}
        </span>
      </div>
      <div className="app-live-body" aria-busy={status === 'checking'}>
        {body}
      </div>
      <p className="app-live-note">AI review runs after you submit.</p>
    </section>
  );
}
