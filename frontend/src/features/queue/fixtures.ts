/*
 * Deterministic queue data for unit tests, e2e stubs, and UI-review screenshots. Pure data (types only), so
 * Playwright can import it too. Ages are relative to `now` so screenshots read "3d" whatever day they run.
 */
import type {
  DecisionOut,
  FindingOut,
  ItemDetailOut,
  ItemFilter,
  ItemRowOut,
  MeOut,
  PartnerRowOut,
  QueueStatFiltersOut,
  QueueStatsOut,
  SavedViewOut,
  UserOut,
} from '../../api/generated/model';

const HOUR = 3_600_000;
const DAY = 24 * HOUR;

export function ago(ms: number, now: Date = new Date()): string {
  return new Date(now.getTime() - ms).toISOString();
}

export const USERS: UserOut[] = [
  {
    id: 2,
    display_name: 'Dana Whitfield',
    email: 'dana@clearpath.demo',
    roles: ['reviewer'],
    is_active: true,
    is_available: true,
  },
  {
    id: 3,
    display_name: 'Sam Okafor',
    email: 'sam@clearpath.demo',
    roles: ['reviewer'],
    is_active: true,
    is_available: true,
  },
  {
    id: 4,
    display_name: 'Priya Raman',
    email: 'lead@clearpath.demo',
    roles: ['lead', 'reviewer'],
    is_active: true,
    is_available: true,
  },
];

export const ME_REVIEWER: MeOut = {
  id: 2,
  display_name: 'Dana Whitfield',
  email: 'dana@clearpath.demo',
  roles: ['reviewer'],
  effective_roles: ['reviewer'],
  is_available: true,
};

export const ME_LEAD: MeOut = {
  id: 4,
  display_name: 'Priya Raman',
  email: 'lead@clearpath.demo',
  roles: ['lead'],
  effective_roles: ['lead', 'reviewer'],
  is_available: true,
};

export const ME_MARKETER: MeOut = {
  id: 7,
  display_name: 'Jordan Ellis',
  email: 'marketer@clearpath.demo',
  roles: ['marketer'],
  effective_roles: ['marketer'],
  is_available: true,
};

function partner(id: number, name: string, type: PartnerRowOut['type']): PartnerRowOut {
  return {
    id,
    name,
    type,
    status: 'active',
    item_count: 12,
    approved_count: 8,
    open_findings_count: 3,
    last_submitted_at: null,
  };
}

export const PARTNERS: PartnerRowOut[] = [
  partner(11, 'LendStack', 'marketplace'),
  partner(12, 'CreditCompass', 'affiliate'),
  partner(13, 'RateRadar', 'lead_gen'),
];

const dana = { id: 2, name: 'Dana Whitfield' };
const sam = { id: 3, name: 'Sam Okafor' };
const jordan = { id: 7, name: 'Jordan Ellis' };

export function makeRow(overrides: Partial<ItemRowOut> = {}, now: Date = new Date()): ItemRowOut {
  const id = overrides.id ?? 1042;
  return {
    id,
    key: `CP-${String(id)}`,
    title: 'Spring personal loan email',
    status: 'in_review',
    risk_tier: 'medium',
    product: 'personal_loan',
    channel: 'email',
    partner: null,
    owner: jordan,
    assignee: dana,
    open_findings_count: 2,
    age_days: 3,
    round: 1,
    reopen_reason: null,
    llm_check_status: 'succeeded',
    is_legacy: false,
    markets: ['national', 'CA'],
    tags: [],
    notes: '',
    current_version_n: 1,
    planned_first_run: '2026-11-01',
    planned_last_run: null,
    approval_expires_at: null,
    latest_decision: null,
    submitted_at: ago(3 * DAY + 2 * HOUR, now),
    updated_at: ago(5 * HOUR, now),
    ...overrides,
  };
}

/** A realistic first page of a reviewer's queue, already in queue order (re-reviews, then risk, then age). */
export function queueRows(now: Date = new Date()): ItemRowOut[] {
  const r = (o: Partial<ItemRowOut>, days: number) =>
    makeRow({ ...o, age_days: days, submitted_at: ago(days * DAY + 3 * HOUR, now) }, now);
  return [
    r(
      {
        id: 1031,
        title: 'CreditCompass card comparison page — 0% intro APR',
        status: 'needs_rereview',
        risk_tier: 'high',
        product: 'credit_card',
        channel: 'affiliate_page',
        partner: { id: 12, name: 'CreditCompass' },
        reopen_reason: 'terms_changed',
        round: 2,
        current_version_n: 3,
        open_findings_count: 0,
        tags: ['terms-v13'],
      },
      9,
    ),
    r(
      {
        id: 1038,
        title: 'Prequal landing page — “see your rate in minutes”',
        status: 'in_review',
        risk_tier: 'high',
        product: 'mortgage_prequal',
        channel: 'landing_page',
        reopen_reason: 'approval_expired',
        round: 2,
        open_findings_count: 1,
      },
      6,
    ),
    r(
      {
        id: 1044,
        title: 'LendStack marketplace tile — debt consolidation',
        status: 'submitted',
        risk_tier: 'high',
        channel: 'affiliate_page',
        partner: { id: 11, name: 'LendStack' },
        assignee: null,
        open_findings_count: 4,
      },
      5,
    ),
    r(
      {
        id: 1047,
        title: 'RateRadar lead-gen form copy',
        status: 'in_review',
        risk_tier: 'high',
        channel: 'affiliate_page',
        partner: { id: 13, name: 'RateRadar' },
        open_findings_count: 3,
        round: 3,
        current_version_n: 3,
      },
      4,
    ),
    r(
      {
        id: 1050,
        title: 'Card balance-transfer paid social carousel',
        status: 'submitted',
        risk_tier: 'medium',
        product: 'credit_card',
        channel: 'paid_social',
        assignee: sam,
        open_findings_count: 2,
        tags: ['q4-launch'],
      },
      3,
    ),
    r(
      {
        id: 1052,
        title: 'Personal loan search ads — “rates from 8.99% APR”',
        status: 'in_review',
        risk_tier: 'medium',
        channel: 'paid_search',
        open_findings_count: 1,
      },
      2,
    ),
    r(
      {
        id: 1055,
        title: 'Spring personal loan email',
        status: 'submitted',
        risk_tier: 'low',
        channel: 'email',
        open_findings_count: 0,
      },
      1,
    ),
    r(
      {
        id: 1058,
        title: 'Branch call script — card activation upsell',
        status: 'in_review',
        risk_tier: 'low',
        product: 'credit_card',
        channel: 'call_script',
        open_findings_count: 0,
        round: 2,
        current_version_n: 2,
      },
      0,
    ),
  ];
}

/**
 * An ItemFilter as the API serializes it: every field present, defaults included (pydantic dumps them all).
 * Copied from `GET /items/stats` on the backend (reviews.selectors.queue_stat_filters), so the views' tests
 * read the shape the server really sends.
 */
export function serverFilter(overrides: Partial<ItemFilter>): ItemFilter {
  return {
    q: null,
    status: [],
    product: [],
    channel: [],
    partner_id: [],
    assignee_id: [],
    owner_id: [],
    mine: false,
    submitted_by_me: false,
    unassigned: false,
    risk_tier: [],
    market: [],
    tag: [],
    is_legacy: null,
    has_open_findings: null,
    reopen_reason: [],
    submitted_after: null,
    submitted_before: null,
    waiting_more_than_days: null,
    approved_after: null,
    approved_before: null,
    approved_within_days: null,
    run_from: null,
    run_to: null,
    ...overrides,
  };
}

const QUEUED: ItemFilter['status'] = ['submitted', 'in_review', 'needs_rereview'];

export const STAT_FILTERS: QueueStatFiltersOut = {
  open: serverFilter({ status: QUEUED, is_legacy: false }),
  mine: serverFilter({ status: QUEUED, is_legacy: false, mine: true }),
  unassigned: serverFilter({ status: QUEUED, is_legacy: false, unassigned: true }),
  needs_rereview: serverFilter({ status: ['needs_rereview'], is_legacy: false }),
  waiting_over_3_days: serverFilter({ status: QUEUED, is_legacy: false, waiting_more_than_days: 3 }),
};

export const STATS: QueueStatsOut = {
  open: 23,
  mine: 8,
  unassigned: 4,
  needs_rereview: 2,
  waiting_over_3_days: 6,
  by_status: (
    [
      ['submitted', 9],
      ['in_review', 12],
      ['changes_requested', 5],
      ['needs_rereview', 2],
      ['approved', 31],
    ] as const
  ).map(([status, count]) => ({
    status,
    count,
    filters: serverFilter({ status: [status], is_legacy: false }),
  })),
  filters: STAT_FILTERS,
};

export const AFFILIATE_VIEW: SavedViewOut = {
  id: 21,
  name: 'Affiliate, high risk',
  created_at: '2026-10-01T09:00:00Z',
  filters: { channel: ['affiliate_page'], risk_tier: ['high'] },
  sort: 'queue',
  columns: [],
};

export const SAVED_VIEWS: SavedViewOut[] = [AFFILIATE_VIEW];

export function makeFinding(overrides: Partial<FindingOut> = {}): FindingOut {
  return {
    id: 1,
    rule_id: 'regz.trigger_terms',
    citation: 'Reg Z 1026.24(d)',
    source: 'code',
    severity: 'blocking',
    state: 'open',
    message: 'Trigger term needs the full APR disclosure',
    suggested_fix: 'Add the APR range and repayment terms.',
    quote: 'rates from 8.99%',
    span: { start: 10, end: 26 },
    reason: '',
    resolved_at: null,
    resolved_by: null,
    carried_from_id: null,
    created_at: '2026-10-20T10:00:00Z',
    version_n: 1,
    ...overrides,
  };
}

export const FINDINGS: FindingOut[] = [
  makeFinding({ id: 1 }),
  makeFinding({
    id: 2,
    severity: 'blocking',
    rule_id: 'ca.22162_license',
    citation: 'Cal. Fin. Code §22162',
  }),
  makeFinding({ id: 3, severity: 'warning', source: 'llm', rule_id: 'llm.as_low_as' }),
  makeFinding({ id: 4, severity: 'warning', state: 'dismissed', reason: 'Qualifier is in the footer' }),
];

export function makeDecision(overrides: Partial<DecisionOut> = {}): DecisionOut {
  return {
    id: 90,
    outcome: 'changes_requested',
    lane: 'standard',
    approver: { id: 2, name: 'Dana Whitfield' },
    reason: 'Add the APR range next to the rate claim.',
    decided_at: '2026-10-18T15:30:00Z',
    expires_at: null,
    ruleset_date: '2026-10-01',
    engine_version: '',
    evidence: [],
    terms_versions: [],
    ai_review_carried_from_n: null,
    llm_override_reason: null,
    version_n: 1,
    ...overrides,
  };
}

export function makeDetail(row: ItemRowOut, overrides: Partial<ItemDetailOut> = {}): ItemDetailOut {
  return {
    ...row,
    approval_expires_at: null,
    approved_at: null,
    current_version: null,
    is_prescreen: false,
    latest_decision: null,
    legacy_history: '',
    legacy_ref: null,
    legacy_reviewer: '',
    legacy_submitter: '',
    live_placements_count: 0,
    numbers_change: null,
    llm_check_failure_code: null,
    llm_check_failure_reason: null,
    drift_rereview: null,
    notes: '',
    retention_until: null,
    risk_tier_overridden: false,
    source_url: null,
    versions: [],
    ...overrides,
  };
}
