/*
 * Hand-built fixtures for Offer terms and Partners. No MSW imports: Playwright e2e and the screenshot spec reuse
 * this file. Numbers follow F's worked example (PL APR 7.49% → 12.99%; "14 approved items quote v12").
 */
import type {
  AffectedItemOut,
  AttachmentOut,
  ImpactPreviewOut,
  ItemRowOut,
  MeOut,
  OfferTermsOut,
  PartnerDetailOut,
  PartnerFindingOut,
  PartnerRowOut,
} from '../../api/generated/model';

export const LEAD_ME: MeOut = {
  id: 4,
  email: 'lead@clearpath.demo',
  display_name: 'Priya Raman',
  roles: ['lead'],
  effective_roles: ['lead', 'reviewer'],
  is_available: true,
};

export const REVIEWER_ME: MeOut = {
  id: 2,
  email: 'reviewer@clearpath.demo',
  display_name: 'Dana Reyes',
  roles: ['reviewer'],
  effective_roles: ['reviewer'],
  is_available: true,
};

const lead = { id: 4, name: 'Priya Raman' };
const reviewer = { id: 2, name: 'Dana Reyes' };
const marketer = { id: 11, name: 'Jordan Ellis' };

// ---- Offer terms -------------------------------------------------------------------------------------

export const PL_V12: OfferTermsOut = {
  id: 112,
  product: 'personal_loan',
  version: 12,
  effective_from: '2026-10-02T14:00:00Z',
  effective_to: null,
  values: {
    product: 'personal_loan',
    apr_min: '7.49',
    apr_max: '35.99',
    amount_min: '1000',
    amount_max: '50000',
    term_months: [24, 36, 60],
    origination_fee_min_pct: '0',
    origination_fee_max_pct: '8',
  },
  note: 'Q4 rate card.',
  created_by_id: lead.id,
  created_by_name: lead.name,
  created_at: '2026-10-02T14:00:00Z',
  is_current: true,
};

export const PL_V11: OfferTermsOut = {
  ...PL_V12,
  id: 111,
  version: 11,
  effective_from: '2026-07-01T13:00:00Z',
  effective_to: '2026-10-02T14:00:00Z',
  values: { ...PL_V12.values, apr_min: '6.99', term_months: [36, 60] },
  note: '',
  created_by_name: 'Sam Okafor',
  created_at: '2026-07-01T13:00:00Z',
  is_current: false,
};

export const PL_V10: OfferTermsOut = {
  ...PL_V11,
  id: 110,
  version: 10,
  effective_from: '2026-03-01T14:00:00Z',
  effective_to: '2026-07-01T13:00:00Z',
  values: { ...PL_V11.values, origination_fee_max_pct: '6' },
  note: 'Launch terms.',
  created_at: '2026-03-01T14:00:00Z',
};

export const CC_V4: OfferTermsOut = {
  id: 204,
  product: 'credit_card',
  version: 4,
  effective_from: '2026-09-15T14:00:00Z',
  effective_to: null,
  values: {
    product: 'credit_card',
    purchase_apr_min: '19.24',
    purchase_apr_max: '29.24',
    purchase_apr_variable: true,
    intro_apr: '0',
    intro_months: 15,
    balance_transfer_fee_pct: '3',
    annual_fee: '0',
    issuing_bank: 'Coastal Community Bank',
  },
  note: '',
  created_by_id: lead.id,
  created_by_name: lead.name,
  created_at: '2026-09-15T14:00:00Z',
  is_current: true,
};

export const CURRENT_TERMS: OfferTermsOut[] = [PL_V12, CC_V4];
export const PL_HISTORY: OfferTermsOut[] = [PL_V12, PL_V11, PL_V10];
export const CC_HISTORY: OfferTermsOut[] = [CC_V4];

function affectedRow(o: Partial<ItemRowOut> & { id: number; title: string }): ItemRowOut {
  return {
    key: `CP-${String(o.id)}`,
    status: 'approved',
    risk_tier: 'medium',
    product: 'personal_loan',
    channel: 'email',
    partner: null,
    owner: marketer,
    assignee: reviewer,
    open_findings_count: 0,
    age_days: 30,
    round: 1,
    reopen_reason: null,
    llm_check_status: 'succeeded',
    is_legacy: false,
    markets: ['national'],
    tags: [],
    current_version_n: 2,
    planned_first_run: '2026-10-01',
    planned_last_run: null,
    submitted_at: '2026-09-20T14:00:00Z',
    updated_at: '2026-09-25T14:00:00Z',
    ...o,
  };
}

const MORE_TITLES = [
  'Debt consolidation email, fall',
  'Personal loan paid search ad A',
  'Personal loan paid search ad B',
  'Home improvement landing page',
  'Rate check display banner',
  'Wedding loan social carousel',
  'Medical expense loan email',
  'Credit card payoff landing page',
  'Personal loan direct mail insert',
  'Summer travel loan SMS',
  'Car repair loan display ad',
];

/** Eleven more affected items, so the preview's 14 = its table's 14 (7 more live, 4 more not). */
const MORE_AFFECTED: AffectedItemOut[] = MORE_TITLES.map((title, index) => {
  const live = index < 7;
  return {
    item: affectedRow({
      id: 1060 + index,
      title,
      channel: index % 3 === 0 ? 'email' : index % 3 === 1 ? 'paid_search' : 'display',
      partner: index === 2 || index === 5 ? { id: 31, name: 'LoanFinder' } : null,
    }),
    is_live: live,
    quoted_fields: index % 2 === 0 ? ['apr_min', 'apr_max'] : ['apr_min', 'example_payment'],
    will_become: live ? 'needs_rereview' : 'expired',
    lane: 'fast_track',
    numbers_change: true,
  };
});

export const IMPACT_PL: ImpactPreviewOut = {
  summary: '14 approved items quote v12; 9 will need re-review, 5 will expire.',
  current_terms_id: PL_V12.id,
  current_version: 12,
  next_version: 13,
  approved_items_quoting: 14,
  will_need_rereview: 9,
  will_expire: 5,
  already_in_rereview: 0,
  normal_lane: 1,
  changed_fields: ['apr_min'],
  items: [
    {
      item: affectedRow({
        id: 1042,
        title: 'Spring personal loan email',
        partner: { id: 31, name: 'LoanFinder' },
        channel: 'affiliate_page',
      }),
      is_live: true,
      quoted_fields: ['apr_min', 'apr_max', 'example_payment'],
      will_become: 'needs_rereview',
      lane: 'fast_track',
      numbers_change: true,
    },
    {
      item: affectedRow({ id: 1043, title: 'Debt consolidation landing page', channel: 'landing_page' }),
      is_live: true,
      quoted_fields: ['apr_max'],
      will_become: 'needs_rereview',
      lane: 'fast_track',
      numbers_change: false,
    },
    {
      item: affectedRow({
        id: 1051,
        title: 'Home improvement paid social',
        channel: 'paid_social',
        partner: { id: 32, name: 'LendStack' },
      }),
      is_live: false,
      quoted_fields: ['apr_min'],
      will_become: 'expired',
      lane: 'normal',
      numbers_change: true,
    },
    ...MORE_AFFECTED,
  ],
  partners: [
    { partner: { id: 31, name: 'LoanFinder' }, item_count: 4 },
    { partner: { id: 32, name: 'LendStack' }, item_count: 2 },
  ],
};

export const IMPACT_NONE: ImpactPreviewOut = {
  ...IMPACT_PL,
  summary: 'No approved items quote v12.',
  approved_items_quoting: 0,
  will_need_rereview: 0,
  will_expire: 0,
  normal_lane: 0,
  items: [],
  partners: [],
};

export const PL_V13: OfferTermsOut = {
  ...PL_V12,
  id: 113,
  version: 13,
  effective_from: '2026-10-24T15:00:00Z',
  values: { ...PL_V12.values, apr_min: '12.99' },
  note: '',
  created_at: '2026-10-24T15:00:00Z',
};

// ---- Partners ----------------------------------------------------------------------------------------

export const PARTNER_ROWS: PartnerRowOut[] = [
  {
    id: 33,
    name: 'CreditMatch',
    type: 'marketplace',
    status: 'paused',
    item_count: 6,
    approved_count: 2,
    open_findings_count: 0,
    last_submitted_at: '2026-08-14T15:00:00Z',
  },
  {
    id: 32,
    name: 'LendStack',
    type: 'lead_gen',
    status: 'active',
    item_count: 11,
    approved_count: 7,
    open_findings_count: 3,
    last_submitted_at: '2026-10-21T15:00:00Z',
  },
  {
    id: 31,
    name: 'LoanFinder',
    type: 'affiliate',
    status: 'active',
    item_count: 24,
    approved_count: 15,
    open_findings_count: 5,
    last_submitted_at: '2026-10-23T11:00:00Z',
  },
  {
    id: 34,
    name: 'RateRadar',
    type: 'affiliate',
    status: 'terminated',
    item_count: 3,
    approved_count: 0,
    open_findings_count: 0,
    last_submitted_at: null,
  },
];

export const PARTNER_ATTACHMENTS: AttachmentOut[] = [
  {
    id: 901,
    kind: 'agreement',
    original_name: 'LoanFinder affiliate agreement 2026.pdf',
    content_type: 'application/pdf',
    size_bytes: 284_311,
    sha256: '9f2c41d0b7e3a8c5f6d1e2b3a4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7',
    uploaded_by: lead,
    uploaded_at: '2026-01-12T16:00:00Z',
    download_url: '/api/attachments/901/download',
  },
  {
    id: 902,
    kind: 'screenshot',
    original_name: 'loanfinder-placement-oct.png',
    content_type: 'image/png',
    size_bytes: 412_002,
    sha256: '1a2b3c4d5e6f708192a3b4c5d6e7f8099f2c41d0b7e3a8c5f6d1e2b3a4c5d6e7',
    uploaded_by: reviewer,
    uploaded_at: '2026-10-18T10:00:00Z',
    download_url: '/api/attachments/902/download',
  },
];

export const PARTNER_DETAIL: PartnerDetailOut = {
  id: 31,
  name: 'LoanFinder',
  type: 'affiliate',
  status: 'active',
  item_count: 24,
  approved_count: 15,
  open_findings_count: 5,
  last_submitted_at: '2026-10-23T11:00:00Z',
  website: 'https://loanfinder.example.com',
  contact_email: 'compliance@loanfinder.example.com',
  agreement_signed_on: '2026-01-12',
  notes:
    'Comparison site. Placements reviewed monthly; material-connection disclosure required above the fold.',
  created_at: '2025-12-01T15:00:00Z',
  attachments: PARTNER_ATTACHMENTS,
  repeat_issues: [
    {
      rule_id: 'ftc.material_connection',
      citation: '16 CFR 255.5',
      count: 7,
      items: 5,
      last_seen_at: '2026-10-22T15:00:00Z',
    },
    {
      rule_id: 'reg_z.trigger_terms',
      citation: 'Reg Z 1026.24(d)',
      count: 4,
      items: 3,
      last_seen_at: '2026-10-19T15:00:00Z',
    },
  ],
};

export function partnerItemRows(): ItemRowOut[] {
  return [
    affectedRow({
      id: 1042,
      title: 'Spring personal loan comparison page',
      channel: 'affiliate_page',
      partner: { id: 31, name: 'LoanFinder' },
      status: 'in_review',
      open_findings_count: 2,
      submitted_at: '2026-10-23T11:00:00Z',
    }),
    affectedRow({
      id: 1031,
      title: 'Debt consolidation listicle',
      channel: 'affiliate_page',
      partner: { id: 31, name: 'LoanFinder' },
      status: 'approved',
      submitted_at: '2026-09-30T11:00:00Z',
    }),
    affectedRow({
      id: 214,
      title: 'Summer rates comparison (tracker row 88)',
      channel: 'affiliate_page',
      partner: { id: 31, name: 'LoanFinder' },
      status: 'approved',
      is_legacy: true,
      current_version_n: null,
      assignee: null,
      submitted_at: '2025-06-03T00:00:00Z',
    }),
  ];
}

function finding(o: Partial<PartnerFindingOut> & { id: number }): PartnerFindingOut {
  return {
    item_id: 1042,
    item_key: 'CP-1042',
    item_title: 'Spring personal loan comparison page',
    item_is_legacy: false,
    version_n: 2,
    rule_id: 'ftc.material_connection',
    citation: '16 CFR 255.5',
    source: 'code',
    severity: 'blocking',
    state: 'open',
    message: 'No material-connection disclosure near the recommendation.',
    created_at: '2026-10-23T11:05:00Z',
    ...o,
  };
}

export const PARTNER_FINDINGS_PAGE_1: PartnerFindingOut[] = [
  finding({ id: 7001 }),
  finding({
    id: 7000,
    rule_id: 'reg_z.trigger_terms',
    citation: 'Reg Z 1026.24(d)',
    source: 'llm',
    severity: 'warning',
    message: 'Rate claim may need the full APR range.',
  }),
  finding({
    id: 6990,
    item_id: 1031,
    item_key: 'CP-1031',
    item_title: 'Debt consolidation listicle',
    version_n: 1,
    state: 'accepted',
    created_at: '2026-09-30T11:05:00Z',
  }),
];

export const PARTNER_FINDINGS_PAGE_2: PartnerFindingOut[] = [
  finding({
    id: 6900,
    item_id: 1031,
    item_key: 'CP-1031',
    item_title: 'Debt consolidation listicle',
    version_n: 1,
    rule_id: 'udaap.no_credit_check',
    citation: 'CFPA 12 USC 5531',
    source: 'human',
    severity: 'warning',
    state: 'dismissed',
    message: 'Check imagery and layout against the agreement.',
    created_at: '2026-09-29T09:00:00Z',
  }),
];
