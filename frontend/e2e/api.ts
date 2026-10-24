/*
 * API stubs for e2e and UI-review screenshots (no backend, no seed: workstream L owns demo data). Plain data
 * shaped like the generated models; src/features/queue/fixtures.ts holds the typed twin for unit tests (it
 * can't be imported here: e2e compiles under nodenext, which rejects the generated client's import style).
 */
import type { Page, Route } from '@playwright/test';

const DAY = 86_400_000;
const HOUR = 3_600_000;

function ago(ms: number): string {
  return new Date(Date.now() - ms).toISOString();
}

const dana = { id: 2, name: 'Dana Whitfield' };
const sam = { id: 3, name: 'Sam Okafor' };
const jordan = { id: 7, name: 'Jordan Ellis' };

export const ME = {
  reviewer: {
    id: 2,
    display_name: 'Dana Whitfield',
    email: 'reviewer@clearpath.demo',
    roles: ['reviewer'],
    effective_roles: ['reviewer'],
    is_available: true,
  },
  lead: {
    id: 4,
    display_name: 'Priya Raman',
    email: 'lead@clearpath.demo',
    roles: ['lead'],
    effective_roles: ['lead', 'reviewer'],
    is_available: true,
  },
  all: {
    id: 1,
    display_name: 'Demo Admin',
    email: 'admin@clearpath.demo',
    roles: ['marketer', 'reviewer', 'lead', 'admin'],
    effective_roles: ['marketer', 'reviewer', 'lead', 'admin'],
    is_available: true,
  },
} as const;

type Row = Record<string, unknown> & { id: number; status: string };

function row(o: Partial<Row> & { id: number }, days: number): Row {
  return {
    key: `CP-${String(o.id)}`,
    title: 'Spring personal loan email',
    status: 'in_review',
    risk_tier: 'medium',
    product: 'personal_loan',
    channel: 'email',
    partner: null,
    owner: jordan,
    assignee: dana,
    open_findings_count: 2,
    age_days: days,
    round: 1,
    reopen_reason: null,
    llm_check_status: 'succeeded',
    is_legacy: false,
    markets: ['national', 'CA'],
    tags: [],
    current_version_n: 1,
    planned_first_run: '2026-11-01',
    planned_last_run: null,
    submitted_at: ago(days * DAY + 3 * HOUR),
    updated_at: ago(5 * HOUR),
    ...o,
  };
}

export function queueRows(): Row[] {
  return [
    row(
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
    row(
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
    row(
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
    row(
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
    row(
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
    row(
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
    row(
      {
        id: 1055,
        title: 'Spring personal loan email',
        status: 'submitted',
        risk_tier: 'low',
        open_findings_count: 0,
        assignee: null,
      },
      1,
    ),
    row(
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
    row(
      {
        id: 1061,
        title: 'Home equity explainer email — prequal CTA',
        status: 'in_review',
        risk_tier: 'high',
        product: 'mortgage_prequal',
        channel: 'email',
        open_findings_count: 2,
      },
      0,
    ),
    row(
      {
        id: 1063,
        title: 'Direct mail prescreen offer — Q1 wave',
        status: 'submitted',
        risk_tier: 'high',
        product: 'credit_card',
        channel: 'direct_mail',
        open_findings_count: 5,
        assignee: null,
      },
      0,
    ),
  ];
}

export function boardRows(): Row[] {
  return [
    ...queueRows(),
    row(
      {
        id: 1020,
        title: 'Display banner — 6.99% APR personal loans',
        status: 'changes_requested',
        risk_tier: 'medium',
        channel: 'display',
        open_findings_count: 2,
        round: 2,
      },
      8,
    ),
    row(
      {
        id: 1024,
        title: 'CreditCompass email insert — balance transfer',
        status: 'changes_requested',
        risk_tier: 'high',
        product: 'credit_card',
        channel: 'affiliate_page',
        partner: { id: 12, name: 'CreditCompass' },
        open_findings_count: 1,
      },
      7,
    ),
  ];
}

export function approvedRows(): Row[] {
  return [
    row(
      {
        id: 1002,
        title: 'Spring PL landing page refresh',
        status: 'approved',
        risk_tier: 'medium',
        channel: 'landing_page',
        open_findings_count: 0,
        round: 2,
      },
      12,
    ),
    row(
      {
        id: 1009,
        title: 'SMS reminder — application incomplete',
        status: 'approved',
        risk_tier: 'low',
        channel: 'sms',
        open_findings_count: 0,
      },
      10,
    ),
  ];
}

export const STATS = {
  open: 23,
  mine: 8,
  unassigned: 4,
  needs_rereview: 2,
  waiting_over_3_days: 6,
  by_status: [],
};

export const USERS = [
  {
    id: 2,
    display_name: 'Dana Whitfield',
    email: 'reviewer@clearpath.demo',
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

export const PARTNERS = [11, 12, 13].map((id, i) => ({
  id,
  name: ['LendStack', 'CreditCompass', 'RateRadar'][i],
  type: ['marketplace', 'affiliate', 'lead_gen'][i],
  status: 'active',
  item_count: 12,
  approved_count: 8,
  open_findings_count: 3,
  last_submitted_at: null,
}));

const FINDINGS = [
  { severity: 'blocking', state: 'open' },
  { severity: 'blocking', state: 'open' },
  { severity: 'warning', state: 'open' },
  { severity: 'warning', state: 'dismissed' },
].map((f, i) => ({
  id: i + 1,
  rule_id: 'regz.trigger_terms',
  citation: 'Reg Z 1026.24(d)',
  source: 'code',
  message: 'Trigger term needs the full APR disclosure',
  suggested_fix: '',
  quote: 'rates from 8.99%',
  span: { start: 0, end: 10 },
  reason: '',
  resolved_at: null,
  resolved_by: null,
  carried_from_id: null,
  created_at: ago(DAY),
  version_n: 1,
  ...f,
}));

function detail(r: Row) {
  return {
    ...r,
    approval_expires_at: null,
    approved_at: null,
    current_version: null,
    is_prescreen: false,
    latest_decision: {
      id: 90,
      outcome: 'changes_requested',
      lane: 'standard',
      approver: dana,
      reason: 'Add the APR range next to the rate claim, and the CA license line in the footer.',
      decided_at: ago(3 * DAY),
      expires_at: null,
      ruleset_date: '2026-10-01',
      evidence: [],
      terms_versions: [],
      ai_review_carried_from_n: null,
      llm_override_reason: null,
      version_n: 2,
    },
    legacy_history: '',
    legacy_ref: null,
    legacy_reviewer: '',
    legacy_submitter: '',
    live_placements_count: 0,
    notes: 'Partner asked for a rush; launch is 11/1.',
    retention_until: null,
    risk_tier_overridden: false,
    source_url: null,
    versions: [],
  };
}

const RISK_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

/** The server's queue order (backend/reviews/selectors.py): re-reviews first, then risk, then oldest. */
function queueOrder(rows: Row[]): Row[] {
  const rank = (r: Row) => (r.reopen_reason === null ? 10 : 0) + (RISK_RANK[String(r.risk_tier)] ?? 2);
  return [...rows].sort(
    (a, b) => rank(a) - rank(b) || String(a.submitted_at).localeCompare(String(b.submitted_at)),
  );
}

export interface StubOptions {
  me?: object | 'signed-out';
  rows?: Row[];
  /** 'hang' never answers (loading state); a number answers with that status. */
  items?: 'hang' | number;
  /** Counts to serve instead of STATS; 'hang' never answers; a number answers with that status. */
  stats?: 'hang' | number | Partial<typeof STATS>;
  views?: object[] | number;
}

async function fulfill(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

export async function stubApi(page: Page, opts: StubOptions = {}) {
  const rows = opts.rows ?? queueRows();
  const all = [...boardRows(), ...approvedRows(), ...rows];
  await page.route(/\/(api|_allauth)\//, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    if (path === '/api/health') return fulfill(route, { status: 'ok', database: true });
    if (path === '/api/me') {
      if (opts.me === 'signed-out')
        return fulfill(route, { code: 'not_authenticated', message: 'Sign in.' }, 401);
      return fulfill(route, opts.me ?? ME.reviewer);
    }
    if (path.startsWith('/_allauth/')) return fulfill(route, { status: 401 }, 401);
    if (path === '/api/items/stats') {
      if (opts.stats === 'hang') return; // never answers
      if (typeof opts.stats === 'number')
        return fulfill(route, { code: 'x', message: 'Counts are unavailable.' }, opts.stats);
      return fulfill(route, { ...STATS, ...(typeof opts.stats === 'object' ? opts.stats : {}) });
    }
    if (path === '/api/items') {
      const statuses = url.searchParams.getAll('status');
      if (statuses.includes('approved')) return fulfill(route, { rows: approvedRows(), next_cursor: null });
      if (statuses.length === 4) {
        const board = boardRows();
        return fulfill(route, {
          rows: url.searchParams.get('sort') === 'queue' ? queueOrder(board) : board,
          next_cursor: null,
        });
      }
      if (opts.items === 'hang') return;
      if (typeof opts.items === 'number') {
        return fulfill(
          route,
          { code: 'server_error', message: 'The queue is temporarily unavailable. Try again in a minute.' },
          opts.items,
        );
      }
      return fulfill(route, { rows, next_cursor: null });
    }
    if (path === '/api/views') {
      if (typeof opts.views === 'number') return fulfill(route, { code: 'x', message: 'down' }, opts.views);
      return fulfill(route, opts.views ?? []);
    }
    if (path === '/api/users') return fulfill(route, USERS);
    if (path === '/api/partners') return fulfill(route, PARTNERS);
    if (/^\/api\/items\/\d+\/findings$/.test(path)) return fulfill(route, FINDINGS);
    const item = /^\/api\/items\/(\d+)$/.exec(path);
    if (item) {
      const found = all.find((r) => String(r.id) === item[1]);
      if (found === undefined) return fulfill(route, { code: 'not_found', message: 'Not found.' }, 404);
      return fulfill(route, method === 'PATCH' ? found : detail(found));
    }
    return fulfill(route, { code: 'not_found', message: `No stub for ${method} ${path}` }, 404);
  });
}
