/*
 * The decision record as a unit (product-spec "What it does that a spreadsheet can't" #3): what was decided, on
 * which exact version, against which offer-terms versions, rule set and engine, what the AI check contributed,
 * and the evidence relied on with the hash recorded at decision time. Shown in Details for the latest decision
 * and expanded from History for any decision; the evidence pack zip carries the same facts.
 */
import type { DecisionLane, DecisionOut } from '../../api/generated/model';
import { ATTACHMENT_KIND_LABELS, OUTCOME_LABELS, PRODUCT_LABELS, formatDate } from '../../ui/labels';
import { RelativeAge } from '../../ui/RelativeAge';

const LANE_LABELS: Record<DecisionLane, string | null> = {
  standard: null,
  fast_track: 'Fast-track',
  reaffirm: 'Reaffirmed',
};

const isApproval = (d: DecisionOut) => d.outcome === 'approved' || d.outcome === 'approved_with_edits';

/** Characters of a sha256 shown inline; the full hash is the title. */
const SHORT_HASH = 12;

/**
 * What the AI check contributed to an approval (spec §4.2 #4): overridden after a failure (with the reason),
 * carried from an earlier version (fast-track, reviewer edit), or ran on the approved version. Null for
 * decisions the AI gate doesn't apply to.
 */
export function aiReviewLine(d: DecisionOut): string | null {
  if (!isApproval(d)) return null;
  if (d.llm_override_reason !== null && d.llm_override_reason !== '') {
    const carried =
      d.ai_review_carried_from_n === null ? '' : ` (carried from v${String(d.ai_review_carried_from_n)})`;
    return `Overridden${carried}: ${d.llm_override_reason}`;
  }
  if (d.ai_review_carried_from_n !== null) return `Carried from v${String(d.ai_review_carried_from_n)}`;
  return `Ran on v${String(d.version_n)}`;
}

function outcomeLine(d: DecisionOut): string {
  const outcome = OUTCOME_LABELS[d.outcome];
  const on = isApproval(d) ? ' ' : ' on ';
  const lane = LANE_LABELS[d.lane];
  return `${outcome}${on}v${String(d.version_n)}${lane === null ? '' : ` · ${lane}`}`;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="app-detail-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function DecisionRecord({ decision: d }: { decision: DecisionOut }) {
  const approval = isApproval(d);
  const ai = aiReviewLine(d);
  return (
    <dl className="app-details app-decision-record">
      <Row label="Outcome">{outcomeLine(d)}</Row>
      <Row label="Decided by">
        {d.approver.name} · {formatDate(d.decided_at)} · <RelativeAge at={d.decided_at} />
      </Row>
      <Row label="Reason">
        <span className="app-decision-record-reason">{d.reason}</span>
      </Row>
      {approval && (
        <Row label="Offer terms">
          {d.terms_versions.length === 0 ? (
            'None quoted'
          ) : (
            <ul className="app-plain-list">
              {d.terms_versions.map((t) => (
                <li key={t.id} className="app-figure">
                  {PRODUCT_LABELS[t.product]} v{t.version}
                </li>
              ))}
            </ul>
          )}
        </Row>
      )}
      <Row label="Rule set">{formatDate(d.ruleset_date)}</Row>
      <Row label="Engine">
        <span className="app-figure">{d.engine_version === '' ? 'Not recorded' : d.engine_version}</span>
      </Row>
      {ai !== null && <Row label="AI review">{ai}</Row>}
      {approval && d.expires_at !== null && <Row label="Expires">{formatDate(d.expires_at)}</Row>}
      {approval && (
        <Row label="Evidence">
          {d.evidence.length === 0 ? (
            'None relied on'
          ) : (
            <ul className="app-plain-list">
              {d.evidence.map((e) => (
                <li key={e.attachment_id}>
                  {e.original_name} <span className="app-muted">· {ATTACHMENT_KIND_LABELS[e.kind]}</span>
                  <span className="app-hash" title={e.sha256}>
                    sha256 {e.sha256.slice(0, SHORT_HASH)}…
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Row>
      )}
    </dl>
  );
}
