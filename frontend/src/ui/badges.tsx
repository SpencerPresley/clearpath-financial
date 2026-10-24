/*
 * Status, severity, source, and risk marks. Every one is icon + label (spec §5.2: color is never the
 * only signal); tone carries the §5.2 color meaning and lives in data-tone so tests and CSS share it.
 */
import type { FindingSource, ItemStatus, RiskTier, Severity } from './domain';
import { Icon } from './Icon';
import type { IconKey } from './icons';

export type Tone = 'neutral' | 'info' | 'warning' | 'success' | 'error' | 'alert';

interface Meta {
  label: string;
  tone: Tone;
  icon: IconKey;
}

export const STATUS_META: Record<ItemStatus, Meta> = {
  draft: { label: 'Draft', tone: 'neutral', icon: 'status.draft' },
  submitted: { label: 'Submitted', tone: 'neutral', icon: 'status.submitted' },
  in_review: { label: 'In review', tone: 'info', icon: 'status.in_review' },
  changes_requested: { label: 'Changes requested', tone: 'warning', icon: 'status.changes_requested' },
  approved: { label: 'Approved', tone: 'success', icon: 'status.approved' },
  rejected: { label: 'Rejected', tone: 'error', icon: 'status.rejected' },
  needs_rereview: { label: 'Re-review', tone: 'alert', icon: 'status.needs_rereview' },
  expired: { label: 'Expired', tone: 'neutral', icon: 'status.expired' },
  withdrawn: { label: 'Withdrawn', tone: 'neutral', icon: 'status.withdrawn' },
};

export const SEVERITY_META: Record<Severity, Meta> = {
  blocking: { label: 'Blocking', tone: 'error', icon: 'severity.blocking' },
  warning: { label: 'Warning', tone: 'warning', icon: 'severity.warning' },
};

export const SOURCE_META: Record<FindingSource, { label: string; icon: IconKey }> = {
  code: { label: 'Code check', icon: 'source.code' },
  llm: { label: 'AI suggestion', icon: 'source.ai' },
  human: { label: 'Checklist', icon: 'source.human' },
};

// Risk tier is an attribute, not a workflow state, so it takes no status color: direction glyph + label.
export const RISK_META: Record<RiskTier, { label: string; icon: IconKey }> = {
  high: { label: 'High risk', icon: 'risk.high' },
  medium: { label: 'Medium risk', icon: 'risk.medium' },
  low: { label: 'Low risk', icon: 'risk.low' },
};

function Badge({ meta, className = 'app-badge' }: { meta: Meta; className?: string }) {
  return (
    <span className={className} data-tone={meta.tone}>
      <Icon name={meta.icon} size={14} />
      <span>{meta.label}</span>
    </span>
  );
}

export function StatusBadge({ status }: { status: ItemStatus }) {
  return <Badge meta={STATUS_META[status]} />;
}

/**
 * Icon-only status for dense cells (board cards, narrow columns), spec §5.2a: tone + glyph, named by its label
 * for assistive tech and by `title` on hover. No tooltip trigger: inside a keyboard-navigated row a per-cell
 * tab stop would break j/k navigation, so the row is the tab stop and this is announced with it.
 */
export function StatusMark({ status }: { status: ItemStatus }) {
  const meta = STATUS_META[status];
  return (
    <span
      role="img"
      aria-label={meta.label}
      title={meta.label}
      className="app-status-mark"
      data-tone={meta.tone}
    >
      <Icon name={meta.icon} size={14} />
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge meta={SEVERITY_META[severity]} />;
}

export function SourceTag({ source }: { source: FindingSource }) {
  const meta = SOURCE_META[source];
  return (
    <span className="app-source" data-source={source}>
      <Icon name={meta.icon} size={14} />
      <span>{meta.label}</span>
    </span>
  );
}

const RISK_SHORT: Record<RiskTier, string> = { high: 'High', medium: 'Medium', low: 'Low' };

/** `short` drops "risk" from the label where a column header already says Risk (dense tables). */
export function RiskTierBadge({ tier, short = false }: { tier: RiskTier; short?: boolean }) {
  const meta = { ...RISK_META[tier], tone: 'neutral' as const };
  return (
    <Badge
      meta={short ? { ...meta, label: RISK_SHORT[tier] } : meta}
      className="app-badge app-badge-outline"
    />
  );
}
