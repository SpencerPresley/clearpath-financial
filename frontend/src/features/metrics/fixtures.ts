/* Test fixtures for the metrics page: real-shaped responses, numbers chosen so each assertion is unique. */
import type {
  MeOut,
  MetricItemsOut,
  MetricSeriesOut,
  MetricsSummaryOut,
  PartnerRowOut,
} from '../../api/generated/model';

export const ME_LEAD: MeOut = {
  id: 3,
  email: 'lead@clearpath.demo',
  display_name: 'Rachel Okafor',
  roles: ['lead'],
  effective_roles: ['lead', 'reviewer'],
  is_available: true,
};

export const SUMMARY: MetricsSummaryOut = {
  period_from: '2026-07-26',
  period_to: '2026-10-24',
  time_to_first_review: {
    count: 42,
    median_hours: 5,
    p90_hours: 30,
    native_count: 30,
    imported_count: 12,
    native_median_hours: 4,
    imported_median_hours: 216,
  },
  time_per_round: {
    count: 51,
    median_hours: 7.5,
    p90_hours: 52,
    native_count: 51,
    imported_count: 0,
    native_median_hours: 7.5,
    imported_median_hours: null,
  },
  rounds_per_item: {
    count: 18,
    mean: 1.75,
    median: 2,
    native_count: 11,
    imported_count: 7,
    native_mean: 1.4,
    imported_mean: 2.3,
  },
  time_to_fix_live: {
    count: 3,
    median_hours: 26,
    p90_hours: 70,
    native_count: 3,
    imported_count: 0,
    native_median_hours: 26,
    imported_median_hours: null,
  },
  open_fix_live: { count: 2, in_rereview: 1, awaiting_takedown: 1, oldest_hours: 75 },
  throughput: { count: 64, native_count: 57, imported_count: 7, per_week: 4.92 },
  waiting: [
    { more_than_days: 3, count: 9 },
    { more_than_days: 7, count: 4 },
    { more_than_days: 14, count: 1 },
    { more_than_days: 30, count: 0 },
  ],
  imported_from: '2025-01-06',
  imported_to: '2026-08-14',
};

export const EMPTY_SUMMARY: MetricsSummaryOut = {
  ...SUMMARY,
  time_to_first_review: {
    count: 0,
    median_hours: null,
    p90_hours: null,
    native_count: 0,
    imported_count: 0,
    native_median_hours: null,
    imported_median_hours: null,
  },
  time_per_round: {
    count: 0,
    median_hours: null,
    p90_hours: null,
    native_count: 0,
    imported_count: 0,
    native_median_hours: null,
    imported_median_hours: null,
  },
  rounds_per_item: {
    count: 0,
    mean: null,
    median: null,
    native_count: 0,
    imported_count: 0,
    native_mean: null,
    imported_mean: null,
  },
  time_to_fix_live: {
    count: 0,
    median_hours: null,
    p90_hours: null,
    native_count: 0,
    imported_count: 0,
    native_median_hours: null,
    imported_median_hours: null,
  },
  open_fix_live: { count: 0, in_rereview: 0, awaiting_takedown: 0, oldest_hours: null },
  throughput: { count: 0, native_count: 0, imported_count: 0, per_week: 0 },
  waiting: SUMMARY.waiting.map((w) => ({ ...w, count: 0 })),
};

export const SERIES: MetricSeriesOut = {
  metric: 'throughput',
  bucket: 'week',
  period_from: '2026-10-05',
  period_to: '2026-10-24',
  points: [
    {
      period_start: '2026-10-05',
      from_date: '2026-10-05',
      to_date: '2026-10-11',
      value: 6,
      native_value: 4,
      imported_value: 2,
      count: 6,
      native_count: 4,
      imported_count: 2,
    },
    {
      period_start: '2026-10-12',
      from_date: '2026-10-12',
      to_date: '2026-10-18',
      value: 0,
      native_value: 0,
      imported_value: 0,
      count: 0,
      native_count: 0,
      imported_count: 0,
    },
    {
      period_start: '2026-10-19',
      from_date: '2026-10-19',
      to_date: '2026-10-24',
      value: 11,
      native_value: 11,
      imported_value: 0,
      count: 11,
      native_count: 11,
      imported_count: 0,
    },
  ],
};

export const EMPTY_SERIES: MetricSeriesOut = {
  ...SERIES,
  points: SERIES.points.map((p) => ({
    ...p,
    value: 0,
    native_value: 0,
    imported_value: 0,
    count: 0,
    native_count: 0,
    imported_count: 0,
  })),
};

export const ITEMS: MetricItemsOut = {
  metric: 'time_to_first_review',
  total: 2,
  rows: [
    {
      item: {
        id: 17,
        key: 'CP-17',
        title: 'Debt consolidation landing page',
        status: 'approved',
        product: 'personal_loan',
        channel: 'landing_page',
        is_legacy: true,
        legacy_ref: 'MCR-25-031',
        partner_name: null,
      },
      source: 'imported',
      start: '2025-03-03T00:00:00Z',
      end: '2025-03-06T00:00:00Z',
      value: 72,
      outcome: null,
    },
    {
      item: {
        id: 1042,
        key: 'CP-1042',
        title: 'Spring PL email',
        status: 'in_review',
        product: 'personal_loan',
        channel: 'email',
        is_legacy: false,
        legacy_ref: null,
        partner_name: 'LoanFinder',
      },
      source: 'native',
      start: '2026-10-20T09:00:00Z',
      end: '2026-10-20T14:00:00Z',
      value: 5,
      outcome: null,
    },
  ],
};

export const PARTNERS: PartnerRowOut[] = [
  {
    id: 4,
    name: 'LoanFinder',
    type: 'affiliate',
    status: 'active',
    item_count: 12,
    approved_count: 9,
    open_findings_count: 1,
    last_submitted_at: '2026-10-20T09:00:00Z',
  },
];

const NATIVE_ITEM = {
  id: 1042,
  key: 'CP-1042',
  title: 'Spring PL email',
  status: 'in_review',
  product: 'personal_loan',
  channel: 'email',
  is_legacy: false,
  legacy_ref: null,
  partner_name: 'LoanFinder',
} as const;

/** The still-open fix-live clocks: no end, value = hours open so far. */
export const OPEN_ITEMS: MetricItemsOut = {
  metric: 'time_to_fix_live',
  total: 2,
  rows: [
    {
      item: {
        ...NATIVE_ITEM,
        id: 1050,
        key: 'CP-1050',
        title: 'Balance transfer display ad',
        status: 'needs_rereview',
      },
      source: 'native',
      start: '2026-10-21T09:00:00Z',
      end: null,
      value: 75,
      outcome: null,
    },
    {
      item: {
        ...NATIVE_ITEM,
        id: 1033,
        key: 'CP-1033',
        title: 'Spring PL affiliate page',
        status: 'withdrawn',
      },
      source: 'native',
      start: '2026-10-23T13:00:00Z',
      end: null,
      value: 20,
      outcome: null,
    },
  ],
};
