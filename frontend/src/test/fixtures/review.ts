/*
 * Hand-built review fixtures with real-ish copy. Finding spans are Python-style code-point offsets that
 * actually index into the copy (the generated faker mocks' spans don't), and the copy has an emoji before
 * every finding so a UTF-16 slip shows up as a misplaced highlight. No MSW imports: Playwright e2e reuses
 * this file (handlers live in reviewHandlers.ts).
 */
import type {
  AttachmentOut,
  CommentOut,
  DecisionOut,
  FindingOut,
  ItemDetailOut,
  ItemHistoryOut,
  ItemRowOut,
  PlacementOut,
  VersionOut,
  VersionSummaryOut,
} from '../../api/generated/model';

export const NOW = '2026-10-24T15:00:00Z';

export const MARKETER = { id: 11, name: 'Priya Natarajan' };
export const REVIEWER = { id: 21, name: 'Dana Reyes' };

export const COPY_V1 = [
  'Need cash fast? 💸 Personal loans as low as 5.99% APR.',
  'Check your rate in 2 minutes with no impact on your credit score.',
  'Loans from $2,000 to $40,000.',
].join('\n');

export const COPY_V2 = [
  'Need cash fast? 💸 Personal loans as low as 5.99% APR.',
  'Check your rate in 2 minutes with no impact on your credit score.',
  'Loans from $2,000 to $40,000. Terms 24–60 months.',
  'ClearPath Financial, Inc. is licensed by the California DFPI under the California Financing Law,',
  'license 60DBO-12345.',
].join('\n');

/** Code-point span of `quote` in `text` (what the backend sends). Throws if absent, so fixtures can't drift. */
export function spanOf(text: string, quote: string, from = 0): { start: number; end: number } {
  const index = text.indexOf(quote, from);
  if (index === -1) {
    throw new Error(`"${quote}" is not in the fixture copy`);
  }
  const start = Array.from(text.slice(0, index)).length;
  return { start, end: start + Array.from(quote).length };
}

const v1Summary: VersionSummaryOut = {
  id: 501,
  n: 1,
  origin: 'submission',
  author: MARKETER,
  created_at: '2026-10-20T14:00:00Z',
  based_on_n: null,
};
const v2Summary: VersionSummaryOut = {
  id: 502,
  n: 2,
  origin: 'submission',
  author: MARKETER,
  created_at: '2026-10-23T16:30:00Z',
  based_on_n: 1,
};

export function versionFixture(n: 1 | 2, overrides: Partial<VersionOut> = {}): VersionOut {
  const summary = n === 1 ? v1Summary : v2Summary;
  const content = n === 1 ? COPY_V1 : COPY_V2;
  return {
    ...summary,
    content_text: content,
    content_sha256: `sha-v${String(n)}`,
    terms_refs: [
      {
        field: 'apr_min',
        span: spanOf(content, '5.99%'),
        quote: '5.99%',
        quoted_value: '5.99',
        offer_terms: { id: 12, product: 'personal_loan', version: 12 },
      },
    ],
    ...overrides,
  };
}

export function itemFixture(overrides: Partial<ItemDetailOut> = {}): ItemDetailOut {
  return {
    id: 1042,
    key: 'CP-1042',
    title: 'Fall personal loan promo — paid social',
    product: 'personal_loan',
    channel: 'paid_social',
    status: 'in_review',
    round: 2,
    risk_tier: 'medium',
    reopen_reason: null,
    llm_check_status: 'succeeded',
    is_legacy: false,
    markets: ['national', 'CA'],
    tags: ['fall-promo'],
    open_findings_count: 3,
    submitted_at: '2026-10-20T14:00:00Z',
    updated_at: '2026-10-23T16:30:00Z',
    queue_entered_at: '2026-10-20T14:00:00Z',
    age_days: 4,
    planned_first_run: '2026-11-01',
    planned_last_run: '2026-12-15',
    current_version_n: 2,
    partner: null,
    owner: MARKETER,
    assignee: REVIEWER,
    notes: '',
    is_prescreen: false,
    risk_tier_overridden: false,
    source_url: null,
    legacy_ref: null,
    legacy_submitter: '',
    legacy_reviewer: '',
    legacy_history: '',
    approved_at: null,
    approval_expires_at: null,
    retention_until: null,
    current_version: versionFixture(2),
    versions: [v1Summary, v2Summary],
    latest_decision: null,
    live_placements_count: 0,
    numbers_change: null,
    llm_check_failure_code: null,
    llm_check_failure_reason: null,
    drift_rereview: null,
    ...overrides,
  };
}

const ROW_KEYS = [
  'id',
  'key',
  'title',
  'product',
  'channel',
  'status',
  'round',
  'risk_tier',
  'reopen_reason',
  'llm_check_status',
  'is_legacy',
  'legacy_ref',
  'markets',
  'tags',
  'open_findings_count',
  'submitted_at',
  'updated_at',
  'queue_entered_at',
  'age_days',
  'planned_first_run',
  'planned_last_run',
  'current_version_n',
  'notes',
  'approval_expires_at',
  'latest_decision',
  'partner',
  'owner',
  'assignee',
] as const satisfies readonly (keyof ItemRowOut)[];

/** Fails to compile when ItemRowOut gains a field ROW_KEYS doesn't list (the cast below would hide it). */
export const ROW_KEYS_COMPLETE: [Exclude<keyof ItemRowOut, (typeof ROW_KEYS)[number]>] extends [never]
  ? true
  : never = true;

/** The queue-row projection of an item fixture. */
export function itemRowFixture(overrides: Partial<ItemDetailOut> = {}): ItemRowOut {
  const item = itemFixture(overrides);
  return Object.fromEntries(ROW_KEYS.map((key) => [key, item[key]])) as unknown as ItemRowOut;
}

const BASE_FINDING = {
  version_n: 2,
  state: 'open',
  reason: '',
  resolved_by: null,
  resolved_at: null,
  carried_from_id: null,
  created_at: '2026-10-23T16:30:01Z',
  suggested_fix: '',
} as const;

export const FINDING_RATE: FindingOut = {
  ...BASE_FINDING,
  id: 9001,
  rule_id: 'pricing.as_low_as_range',
  citation: 'Reg Z 12 CFR 1026.24(a), 1026.16(a)',
  source: 'code',
  severity: 'blocking',
  span: spanOf(COPY_V2, 'as low as 5.99% APR'),
  quote: 'as low as 5.99% APR',
  message: 'Rate claim needs the full APR range',
  suggested_fix: 'Show the range: 5.99%–35.99% APR',
};

export const FINDING_QUALIFIER: FindingOut = {
  ...BASE_FINDING,
  id: 9002,
  rule_id: 'llm.as_low_as_qualifier',
  citation: 'CFPB Supervisory Highlights Issue 24 §2.9.1',
  source: 'llm',
  severity: 'warning',
  span: spanOf(COPY_V2, 'as low as'),
  quote: 'as low as',
  message: '“As low as” may need a creditworthiness qualifier',
  suggested_fix: 'Add “for borrowers with excellent credit”',
  created_at: '2026-10-23T16:30:09Z',
};

export const FINDING_CREDIT: FindingOut = {
  ...BASE_FINDING,
  id: 9003,
  rule_id: 'claims.credit_impact',
  citation: 'CFPB Supervisory Highlights Issue 24 §2.8.2; 12 U.S.C. 5536',
  source: 'code',
  severity: 'blocking',
  span: spanOf(COPY_V2, 'no impact on your credit score'),
  quote: 'no impact on your credit score',
  message: 'Credit-impact claim should be limited to checking your rate',
  suggested_fix: 'Checking your rate won’t affect your credit score.',
};

export const FINDING_CHECKLIST: FindingOut = {
  ...BASE_FINDING,
  id: 9004,
  rule_id: 'human.reg_b_discouragement',
  citation: 'Reg B 12 CFR 1002.4(b)',
  source: 'human',
  severity: 'warning',
  span: null,
  quote: null,
  message: 'Check imagery and targeting for discouragement of protected groups',
};

export const FINDINGS_OPEN: FindingOut[] = [
  FINDING_RATE,
  FINDING_CREDIT,
  FINDING_QUALIFIER,
  FINDING_CHECKLIST,
];

export function triaged(findings: readonly FindingOut[]): FindingOut[] {
  return findings.map((finding, index) =>
    index % 2 === 0
      ? { ...finding, state: 'accepted', resolved_by: REVIEWER, resolved_at: NOW }
      : {
          ...finding,
          state: 'dismissed',
          reason: 'Qualifier appears in the landing page footer.',
          resolved_by: REVIEWER,
          resolved_at: NOW,
        },
  );
}

/** Every finding dismissed with a reason: the state in which a plain Approve is allowed. */
export function dismissedAll(findings: readonly FindingOut[]): FindingOut[] {
  return findings.map((finding) => ({
    ...finding,
    state: 'dismissed',
    reason: 'Disclosed in the landing-page footer this ad links to.',
    resolved_by: REVIEWER,
    resolved_at: NOW,
  }));
}

export const ATTACHMENTS: AttachmentOut[] = [
  {
    id: 71,
    kind: 'substantiation',
    original_name: 'rate-sheet-oct.pdf',
    content_type: 'application/pdf',
    size_bytes: 182_344,
    sha256: '4f9c2a1be07d33c1a8e5b2f0d9c4e7a6b3f8e1d2c5a4b7e6f9d8c3b2a1e0f4d7',
    uploaded_by: MARKETER,
    uploaded_at: '2026-10-20T14:01:00Z',
    download_url: '/api/attachments/71/download',
  },
];

export const COMMENTS: CommentOut[] = [
  {
    id: 301,
    version_n: 2,
    author: REVIEWER,
    body: 'Footer disclosure looks right now. Waiting on the APR range.',
    span: null,
    mentions: [],
    created_at: '2026-10-24T09:12:00Z',
  },
];

export const DECISION_CHANGES: DecisionOut = {
  id: 801,
  version_n: 1,
  outcome: 'changes_requested',
  lane: 'standard',
  approver: REVIEWER,
  reason: 'Add the California license line.\n- Rate claim needs the full APR range',
  ruleset_date: '2026-07-21',
  engine_version: '2026.10.1',
  expires_at: null,
  llm_override_reason: null,
  ai_review_carried_from_n: null,
  terms_versions: [],
  evidence: [],
  decided_at: '2026-10-21T11:00:00Z',
};

export const DECISION_APPROVED: DecisionOut = {
  ...DECISION_CHANGES,
  id: 802,
  version_n: 2,
  outcome: 'approved',
  reason: 'Range and license line present; credit-impact claim limited to rate check.',
  expires_at: '2027-04-24T00:00:00Z',
  terms_versions: [{ id: 12, product: 'personal_loan', version: 12 }],
  evidence: [
    {
      attachment_id: 71,
      kind: 'substantiation',
      original_name: 'rate-sheet-oct.pdf',
      sha256: ATTACHMENTS[0]?.sha256 ?? '',
    },
  ],
  decided_at: '2026-10-24T10:00:00Z',
};

export const PLACEMENTS: PlacementOut[] = [
  {
    id: 41,
    approved_version_n: 2,
    location: 'Meta — Fall PL prospecting',
    url: null,
    first_run: '2026-11-01',
    last_run: null,
    monitored: false,
    takedown_state: null,
    takedown_requested_at: null,
    takedown_confirmed_at: null,
    is_live: true,
    created_by: MARKETER,
    created_at: '2026-10-24T12:00:00Z',
  },
];

export const HISTORY: ItemHistoryOut = {
  entries: [
    {
      id: 1,
      type: 'item.submitted',
      actor: MARKETER,
      at: '2026-10-20T14:00:00Z',
      entity: 'item',
      entity_id: 1042,
      from_status: 'draft',
      to_status: 'submitted',
      payload: { version_id: 501, version_n: 1, round: 1, risk_tier: 'medium', content_sha256: 'sha-v1' },
    },
    {
      id: 2,
      type: 'item.assigned',
      actor: null,
      at: '2026-10-20T14:00:01Z',
      entity: 'item',
      entity_id: 1042,
      from_status: null,
      to_status: null,
      payload: { assignee_id: 21, previous_assignee_id: null, mode: 'lowest_load', reason: 'Lowest load' },
    },
    {
      id: 3,
      type: 'decision.recorded',
      actor: REVIEWER,
      at: '2026-10-21T11:00:00Z',
      entity: 'decision',
      entity_id: 801,
      from_status: 'in_review',
      to_status: 'changes_requested',
      payload: {
        decision_id: 801,
        version_id: 501,
        outcome: 'changes_requested',
        lane: 'standard',
        reason: 'Add the California license line.',
        terms_version_ids: [],
        evidence_attachment_ids: [],
        expires_at: null,
      },
    },
    {
      id: 4,
      type: 'item.resubmitted',
      actor: MARKETER,
      at: '2026-10-23T16:30:00Z',
      entity: 'item',
      entity_id: 1042,
      from_status: 'changes_requested',
      to_status: 'submitted',
      payload: { previous_version_id: 501, version_id: 502, version_n: 2, round: 2 },
    },
  ],
};
