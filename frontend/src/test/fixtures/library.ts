/*
 * Library fixtures (approved list, precedent hits, export jobs) for unit tests, e2e stubs, and UI-review
 * screenshots. Pure data, no MSW, so Playwright can import it.
 */
import type {
  ExportOut,
  ItemRowOut,
  MeOut,
  PartnerRowOut,
  SearchHitOut,
  SearchResultsOut,
} from '../../api/generated/model';

export const LIBRARY_NOW = '2026-10-24T15:00:00Z';

function me(id: number, name: string, roles: MeOut['roles'], effective: MeOut['effective_roles']): MeOut {
  return {
    id,
    display_name: name,
    email: `${roles[0] ?? 'user'}@clearpath.demo`,
    roles,
    effective_roles: effective,
    is_available: true,
  };
}

export const ME_LIBRARY_REVIEWER = me(21, 'Dana Reyes', ['reviewer'], ['reviewer']);
export const ME_LIBRARY_MARKETER = me(11, 'Priya Natarajan', ['marketer'], ['marketer']);
export const ME_ADMIN = me(1, 'Morgan Admin', ['admin'], ['admin']);

function partnerRow(id: number, name: string, type: PartnerRowOut['type']): PartnerRowOut {
  return {
    id,
    name,
    type,
    status: 'active',
    item_count: 14,
    approved_count: 9,
    open_findings_count: 2,
    last_submitted_at: null,
  };
}

export const LIBRARY_PARTNERS: PartnerRowOut[] = [
  partnerRow(11, 'LendStack', 'marketplace'),
  partnerRow(12, 'CreditCompass', 'affiliate'),
  partnerRow(13, 'RateRadar', 'lead_gen'),
];

export function libraryRow(overrides: Partial<ItemRowOut> & { id: number }): ItemRowOut {
  return {
    key: `CP-${String(overrides.id)}`,
    title: 'Spring personal loan email',
    product: 'personal_loan',
    channel: 'email',
    status: 'approved',
    round: 1,
    risk_tier: 'medium',
    reopen_reason: null,
    llm_check_status: 'succeeded',
    is_legacy: false,
    markets: ['national'],
    tags: [],
    open_findings_count: 0,
    submitted_at: '2026-09-02T14:00:00Z',
    updated_at: '2026-10-20T16:30:00Z',
    age_days: 52,
    planned_first_run: '2026-11-01',
    planned_last_run: '2026-12-31',
    current_version_n: 2,
    partner: null,
    owner: { id: 11, name: 'Priya Natarajan' },
    assignee: { id: 21, name: 'Dana Reyes' },
    approval_expires_at: null,
    latest_decision: null,
    notes: '',
    ...overrides,
  };
}

export const APPROVED_ROWS: ItemRowOut[] = [
  libraryRow({
    id: 1088,
    title: 'Holiday personal loan email — “check your rate in 2 minutes”',
    channel: 'email',
    planned_first_run: '2026-11-15',
    planned_last_run: '2027-01-15',
  }),
  libraryRow({
    id: 1081,
    title: 'CreditCompass card comparison tile — 0% intro APR',
    product: 'credit_card',
    channel: 'affiliate_page',
    partner: { id: 12, name: 'CreditCompass' },
    planned_first_run: '2026-10-01',
    planned_last_run: null,
  }),
  libraryRow({
    id: 1074,
    title: 'Prequal landing page — rate table refresh',
    product: 'mortgage_prequal',
    channel: 'landing_page',
    planned_first_run: '2026-10-10',
    planned_last_run: '2026-12-31',
  }),
  libraryRow({
    id: 1069,
    title: 'LendStack marketplace tile — debt consolidation',
    channel: 'affiliate_page',
    partner: { id: 11, name: 'LendStack' },
  }),
  libraryRow({
    id: 1052,
    title: 'Personal loan search ads — “rates from 8.99% APR”',
    channel: 'paid_search',
    planned_first_run: '2026-09-15',
    planned_last_run: '2026-11-30',
  }),
  libraryRow({
    id: 1047,
    title: 'Card balance-transfer paid social carousel',
    product: 'credit_card',
    channel: 'paid_social',
  }),
  libraryRow({
    id: 412,
    key: 'CP-412',
    title: 'RateRadar lead-gen form copy (MCR-25-118)',
    channel: 'affiliate_page',
    partner: { id: 13, name: 'RateRadar' },
    is_legacy: true,
    current_version_n: null,
    planned_first_run: null,
    planned_last_run: null,
    owner: null,
    assignee: null,
  }),
  libraryRow({
    id: 407,
    key: 'CP-407',
    title: 'Fall direct mail prescreen offer (MCR-25-104)',
    product: 'credit_card',
    channel: 'direct_mail',
    is_legacy: true,
    current_version_n: null,
    planned_first_run: null,
    planned_last_run: null,
    owner: null,
    assignee: null,
  }),
];

export function searchHit(overrides: Partial<SearchHitOut> & { item_id: number }): SearchHitOut {
  return {
    key: `CP-${String(overrides.item_id)}`,
    title: 'Spring personal loan email',
    status: 'approved',
    product: 'personal_loan',
    channel: 'email',
    partner_name: null,
    version_id: overrides.item_id * 10,
    version_n: 2,
    score: 0.9,
    snippet: [{ text: 'Spring personal loan email', highlighted: false }],
    version_outcome: 'approved',
    version_decided_at: '2026-10-02T15:00:00Z',
    ...overrides,
  };
}

export const PRECEDENT_HITS: SearchHitOut[] = [
  searchHit({
    item_id: 1088,
    title: 'Holiday personal loan email — “check your rate in 2 minutes”',
    snippet: [
      { text: '…Check your rate in 2 minutes. Checking your rate ', highlighted: false },
      { text: "won't affect your credit score", highlighted: true },
      { text: '. Loans from $2,000 to $40,000…', highlighted: false },
    ],
    version_n: 3,
    version_outcome: 'approved_with_edits',
    version_decided_at: '2026-10-19T17:10:00Z',
  }),
  searchHit({
    item_id: 1031,
    title: 'CreditCompass card comparison page — 0% intro APR',
    product: 'credit_card',
    channel: 'affiliate_page',
    partner_name: 'CreditCompass',
    status: 'needs_rereview',
    snippet: [
      { text: '…See if you prequalify in seconds — it ', highlighted: false },
      { text: "won't affect your credit score", highlighted: true },
      { text: '. Intro APR applies to balance transfers…', highlighted: false },
    ],
    version_n: 2,
    version_outcome: 'approved',
    version_decided_at: '2026-08-04T13:00:00Z',
  }),
  searchHit({
    item_id: 961,
    title: 'Summer personal loan landing page',
    channel: 'landing_page',
    status: 'expired',
    snippet: [
      { text: 'Checking your rate ', highlighted: false },
      { text: "won't affect your credit score", highlighted: true },
      { text: ' (a hard inquiry happens only if you accept an offer).', highlighted: false },
    ],
    version_n: 1,
    version_outcome: 'approved',
    version_decided_at: '2026-05-12T15:00:00Z',
  }),
];

export function searchResults(
  hits: SearchHitOut[],
  query = "won't affect your credit score",
  mode: SearchResultsOut['mode'] = 'phrase',
): SearchResultsOut {
  return { hits, query, mode };
}

export function exportJob(overrides: Partial<ExportOut> & { id: number }): ExportOut {
  return {
    kind: 'items_xlsx',
    status: 'pending',
    item_id: null,
    item_count: null,
    filename: null,
    download_url: null,
    error: null,
    created_at: LIBRARY_NOW,
    finished_at: null,
    ...overrides,
  };
}
