/*
 * Import fixtures shaped like the sample tracker (samples/README.md): its real headers, sample values, and the
 * kinds of problems the importer reports. Pure data, no MSW, so Playwright can import it.
 */
import type {
  ImportColumnOut,
  ImportJobOut,
  ImportJobSummaryOut,
  ImportPreviewOut,
  ImportPreviewRowOut,
  ImportProblemOut,
} from '../../api/generated/model';

export const IMPORT_NOW = '2026-10-24T15:00:00Z';
const ADMIN = { id: 1, name: 'Morgan Admin' };

export const SAMPLE_COLUMNS: ImportColumnOut[] = [
  ['Request ID', 'legacy_ref', ['MCR-25-001', 'MCR-25-002', 'MCR-25-003']],
  ['Date Submitted', 'submitted_on', ['11/3/2025', '11/13/2025', '11/14/2025']],
  [
    'Submitter / BU',
    'submitter',
    ['Priya Natarajan / Growth Marketing (PL)', 'Marcus Bell / Card Marketing'],
  ],
  ['Product', 'product', ['Personal Loan', 'Credit Card', 'personal loans']],
  ['Channel', 'channel', ['Direct Mail', 'Paid Social', 'Display']],
  ['Asset Name / File Link', 'title', ['PL Credit Card Payoff postcard', 'CC_CardBrand_DSP_v1.zip']],
  ['Affiliate / Partner', 'partner', ['Money with Maya', 'LendCompare', 'HomeBound Leads']],
  ['Risk Tier', 'risk_tier', ['High', 'Low', 'Medium']],
  ['Trigger Terms Present (Y/N)', 'trigger_terms', ['N', 'Y', 'yes']],
  ['Assigned Reviewer', 'reviewer', ['Leah Brandt', 'Samuel Ortega', 'Dana Kim']],
  ['Version #', 'version_number', ['2', '1', '3']],
  ['Revision Round', 'rounds', ['2', '1', '3']],
  ['Status', 'status', ['Approved', 'Rejected', 'Approved w/ Changes']],
  [
    'Reviewer Comments / Required Changes',
    'comments',
    ["R1 11/11 RO: 'You're pre-approved!' - this is not a prescreened firm offer"],
  ],
  ['Approval Date & Approver', 'approval', ['11/26/25 - L. Brandt', '11/24/25 - S. Ortega']],
  ['Approval Expiration / Re-review Date', 'expires_on', ['12/25/2025', '5/24/2026']],
  [
    'Live URL / Placement & Screenshot Link',
    'placement',
    ['Drop 11/27, 51k pieces', 'Meta campaign PL_CustomerStory_25Q4'],
  ],
].map(([name, field, sample_values]) => ({
  name: name as string,
  sample_values: sample_values as string[],
  suggested_field: field as ImportColumnOut['field'],
  field: field as ImportColumnOut['field'],
}));

export function importJob(overrides: Partial<ImportJobOut> = {}): ImportJobOut {
  return {
    id: 7,
    status: 'uploaded',
    filename: 'clearpath_review_tracker.xlsx',
    sheet_name: 'Review Tracker',
    row_count: 180,
    created_by: ADMIN,
    created_at: '2026-10-24T14:52:00Z',
    updated_at: '2026-10-24T14:52:00Z',
    commit_requested_at: null,
    committed_at: null,
    summary: null,
    error: null,
    columns: SAMPLE_COLUMNS,
    status_values: [
      { source_value: 'Approved', rows: 120, status: 'approved', outcome: 'approved', source: 'default' },
      {
        source_value: 'Changes Requested',
        rows: 6,
        status: 'changes_requested',
        outcome: 'changes_requested',
        source: 'default',
      },
      { source_value: 'In Review', rows: 5, status: 'in_review', outcome: null, source: 'default' },
      { source_value: 'Rejected', rows: 9, status: 'rejected', outcome: 'rejected', source: 'default' },
    ],
    value_mappings: [],
    ...overrides,
  };
}

function problem(
  o: Partial<ImportProblemOut> & Pick<ImportProblemOut, 'kind' | 'severity' | 'message'>,
): ImportProblemOut {
  return { row_number: null, column: null, value: null, ...o };
}

export const SAMPLE_PROBLEMS: ImportProblemOut[] = [
  problem({
    row_number: 19,
    column: 'Request ID',
    kind: 'not_data_row',
    severity: 'info',
    value: 'NOTE: rows below were added after the Q1 audit',
    message: 'Not a tracker row (a note); skipped.',
  }),
  problem({
    row_number: 68,
    column: 'Request ID',
    kind: 'duplicate_row',
    severity: 'info',
    value: 'MCR-25-066',
    message: 'Same as row 67; imported once.',
  }),
  problem({
    row_number: 92,
    column: 'Request ID',
    kind: 'reused_ref',
    severity: 'warning',
    value: 'MCR-25-090',
    message: 'MCR-25-090 is also used on row 91 for a different asset; imported as MCR-25-090-b.',
  }),
  problem({
    row_number: 23,
    column: 'Affiliate / Partner',
    kind: 'fuzzy_partner',
    severity: 'warning',
    value: 'CardPerks',
    message: 'Read “CardPerks” as the partner CardPerks Weekly.',
  }),
  problem({
    row_number: 41,
    column: 'Approval Date & Approver',
    kind: 'derived_approval_date',
    severity: 'warning',
    value: 'L. Brandt',
    message: 'No approval date; used the last comment’s date (Jan 14, 2026).',
  }),
  problem({
    row_number: 57,
    column: 'Approval Expiration / Re-review Date',
    kind: 'missing_expiry',
    severity: 'warning',
    value: null,
    message: 'Approved with no expiration date; imported without one.',
  }),
  problem({
    row_number: 33,
    column: 'Date Submitted',
    kind: 'coerced_date',
    severity: 'info',
    value: 'Jan 7',
    message: 'Read “Jan 7” as Jan 7, 2026 (year from the Request ID).',
  }),
];

function previewRow(o: Partial<ImportPreviewRowOut> & { row_number: number }): ImportPreviewRowOut {
  return {
    action: 'create',
    legacy_ref: `MCR-25-${String(o.row_number - 1).padStart(3, '0')}`,
    title: 'PL Credit Card Payoff postcard',
    status: 'approved',
    outcome: 'approved',
    submitted_on: '2025-11-03',
    partner: null,
    problem_count: 0,
    item_id: null,
    ...o,
  };
}

const ROWS: ImportPreviewRowOut[] = [
  previewRow({ row_number: 2, title: 'PL Credit Card Payoff postcard' }),
  previewRow({
    row_number: 3,
    title: 'Money with Maya - PL Medical Bills social ad',
    partner: 'Money with Maya',
    submitted_on: '2025-11-13',
  }),
  previewRow({
    row_number: 4,
    title: 'CC_CardBrand_DSP_v1.zip',
    status: 'rejected',
    outcome: 'rejected',
    submitted_on: '2025-11-14',
  }),
  previewRow({
    row_number: 5,
    title: 'HomeBound prequal landing page',
    partner: 'HomeBound Leads',
    status: 'in_review',
    outcome: null,
    submitted_on: '2025-11-18',
  }),
  previewRow({
    row_number: 6,
    title: 'LendCompare marketplace tile',
    partner: 'LendCompare',
    status: 'changes_requested',
    outcome: 'changes_requested',
    submitted_on: '2025-11-20',
  }),
  previewRow({
    row_number: 19,
    legacy_ref: null,
    title: null,
    action: 'skip_not_data',
    status: null,
    outcome: null,
    submitted_on: null,
    problem_count: 1,
  }),
  previewRow({ row_number: 68, legacy_ref: 'MCR-25-066', action: 'skip_duplicate', problem_count: 1 }),
];

export function importPreview(overrides: Partial<ImportPreviewOut> = {}): ImportPreviewOut {
  return {
    job_id: 7,
    status: 'mapped',
    counts: { rows_total: 180, ready: 178, duplicates: 1, already_imported: 0, not_data: 1, blocked: 0 },
    problems: SAMPLE_PROBLEMS,
    unmapped: [],
    rows: ROWS,
    ...overrides,
  };
}

/** After commit: each created row carries the item it became (ImportPreviewRowOut.item_id). */
export function committedPreview(): ImportPreviewOut {
  return importPreview({
    status: 'committed',
    rows: ROWS.map((r, i) => (r.action === 'create' ? { ...r, item_id: 400 + i } : r)),
  });
}

/** A file of our own with values the defaults don't know: a status, a partner spelling, a product. */
export const CUSTOM_UNMAPPED: ImportPreviewOut['unmapped'] = [
  { field: 'status', value: 'On Hold', rows: 3 },
  { field: 'partner', value: 'LendCompare Inc.', rows: 2 },
  { field: 'product', value: 'HELOC', rows: 1 },
];

export const CUSTOM_PROBLEMS: ImportProblemOut[] = [
  problem({
    row_number: 12,
    column: 'Status',
    kind: 'unmapped_status',
    severity: 'error',
    value: 'On Hold',
    message: 'Status “On Hold” has no mapping; map it or the row is skipped.',
  }),
  problem({
    row_number: 15,
    column: 'Affiliate / Partner',
    kind: 'unknown_partner',
    severity: 'error',
    value: 'LendCompare Inc.',
    message: 'No partner called “LendCompare Inc.”; map it to a partner or the row is skipped.',
  }),
  ...SAMPLE_PROBLEMS.slice(3, 5),
];

/** The custom file's rows behind CUSTOM_PROBLEMS: unmapped values block 12 and 15; 41 and 57 import with a note. */
export const CUSTOM_ROWS: ImportPreviewRowOut[] = [
  previewRow({ row_number: 12, action: 'blocked', status: null, problem_count: 1 }),
  previewRow({ row_number: 15, action: 'blocked', partner: null, problem_count: 1 }),
  previewRow({ row_number: 41, problem_count: 1 }),
  previewRow({ row_number: 57, problem_count: 1 }),
];

export function recentImports(): ImportJobSummaryOut[] {
  return [
    {
      id: 6,
      status: 'committed',
      filename: 'clearpath_review_tracker.xlsx',
      sheet_name: 'Review Tracker',
      row_count: 180,
      created_by: ADMIN,
      created_at: '2026-10-22T10:05:00Z',
      updated_at: '2026-10-22T10:06:00Z',
      commit_requested_at: '2026-10-22T10:06:00Z',
      committed_at: '2026-10-22T10:06:01Z',
      summary: { created: 178, skipped: 2, partners_created: 8 },
      error: null,
    },
    {
      id: 5,
      status: 'failed',
      filename: 'partner-tracker-2025.xlsx',
      sheet_name: 'Sheet1',
      row_count: 42,
      created_by: ADMIN,
      created_at: '2026-10-21T16:40:00Z',
      updated_at: '2026-10-21T16:41:00Z',
      commit_requested_at: '2026-10-21T16:41:00Z',
      committed_at: null,
      summary: null,
      error: 'The import stopped at row 31: the database was unavailable. Try again.',
    },
  ];
}
