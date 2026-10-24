/*
 * Import vocabulary for the UI. Target labels mirror backend imports.mapping.TARGET_LABELS (the server's
 * messages use the same words); keyed by the generated enums so a new field fails typecheck here.
 */
import type {
  ImportStatus,
  ImportTargetField,
  ImportValueField,
  ItemStatus,
  ProblemSeverity,
} from '../../api/generated/model';
import { Channel, Product, RiskTier } from '../../api/generated/model';
import type { BadgeMeta } from '../../ui/badges';
import { STATUS_META } from '../../ui/badges';
import { CHANNEL_LABELS, PRODUCT_LABELS } from '../../ui/labels';

export const TARGET_LABELS: Record<ImportTargetField, string> = {
  legacy_ref: 'Request ID',
  submitted_on: 'Date submitted',
  submitter: 'Submitter',
  product: 'Product',
  channel: 'Channel',
  title: 'Title',
  partner: 'Partner',
  risk_tier: 'Risk tier',
  trigger_terms: 'Trigger terms',
  reviewer: 'Reviewer',
  version_number: 'Version',
  rounds: 'Rounds',
  status: 'Status',
  comments: 'Comments',
  approval: 'Approval date and approver',
  expires_on: 'Approval expires',
  placement: 'Placement',
  notes: 'Notes',
  ignore: "Don't import",
};

/** Commit refuses without these (backend imports.mapping.REQUIRED_TARGETS). */
export const REQUIRED_TARGETS: readonly ImportTargetField[] = [
  'legacy_ref',
  'submitted_on',
  'title',
  'product',
  'channel',
  'status',
];

/*
 * A finished import is neutral, not success green: green means approved content (§5.2), and an import approves
 * nothing. Label + glyph either way, so tone is never the only signal.
 */
export const IMPORT_STATUS_META: Record<ImportStatus, BadgeMeta> = {
  uploaded: { label: 'Uploaded', tone: 'neutral', icon: 'job.pending' },
  mapped: { label: 'Mapped', tone: 'neutral', icon: 'job.pending' },
  committing: { label: 'Importing', tone: 'info', icon: 'job.running' },
  committed: { label: 'Imported', tone: 'neutral', icon: 'job.done' },
  failed: { label: 'Failed', tone: 'error', icon: 'job.failed' },
};

/** Problem groups by severity. What each row's problem does is the row's Outcome column, not the group. */
export const SEVERITY_GROUPS: readonly { severity: ProblemSeverity; title: string }[] = [
  { severity: 'error', title: 'Errors' },
  { severity: 'warning', title: 'Warnings' },
  { severity: 'info', title: 'Info' },
];

/** Statuses an imported row can take (backend IMPORTABLE_STATUSES). */
const IMPORTABLE: readonly ItemStatus[] = [
  'submitted',
  'in_review',
  'changes_requested',
  'approved',
  'rejected',
];

export interface ValueOption {
  id: string;
  label: string;
}

/** What an unmapped value can import as, per field. Partners come from the app's partner list. */
export function valueOptions(field: ImportValueField | 'status', partners: readonly string[]): ValueOption[] {
  switch (field) {
    case 'status':
      return IMPORTABLE.map((s) => ({ id: s, label: STATUS_META[s].label }));
    case 'product':
      return Object.values(Product).map((p) => ({ id: p, label: PRODUCT_LABELS[p] }));
    case 'channel':
      return Object.values(Channel).map((c) => ({ id: c, label: CHANNEL_LABELS[c] }));
    case 'risk_tier':
      return Object.values(RiskTier).map((r) => ({
        id: r,
        label: `${r.charAt(0).toUpperCase()}${r.slice(1)}`,
      }));
    case 'trigger_terms':
      return [
        { id: 'yes', label: 'Yes' },
        { id: 'no', label: 'No' },
      ];
    case 'partner':
      return partners.map((name) => ({ id: name, label: name }));
  }
}

export const VALUE_FIELD_LABELS: Record<ImportValueField | 'status', string> = {
  status: 'Status',
  product: 'Product',
  channel: 'Channel',
  risk_tier: 'Risk tier',
  partner: 'Partner',
  trigger_terms: 'Trigger terms',
};
