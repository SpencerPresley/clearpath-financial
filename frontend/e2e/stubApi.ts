/*
 * An in-memory stand-in for the API, for e2e flows and UI-review screenshots. It serves the hand-built
 * fixtures from src/test/fixtures/review.ts and applies triage, decisions, and submissions to its own
 * state so a flow can run end to end. `posted` records every write for assertions.
 */
import type { Page, Route } from '@playwright/test';

import type {
  AttachmentOut,
  ItemHistoryOut,
  CheckPreviewIn,
  CheckPreviewOut,
  DecisionIn,
  DecisionOut,
  FindingDraftOut,
  FindingOut,
  ItemDetailOut,
  ItemRowOut,
  PlacementOut,
  SubmitItemIn,
  UserOut,
} from '../src/api/generated/model';
import {
  ATTACHMENTS,
  COMMENTS,
  FINDINGS_OPEN,
  HISTORY,
  MARKETER,
  NOW,
  PLACEMENTS,
  REVIEWER,
  itemFixture,
  itemRowFixture,
  spanOf,
  versionFixture,
} from '../src/test/fixtures/review';
import { wordDiff } from '../src/ui/copy/wordDiff';

export interface StubState {
  item: ItemDetailOut;
  findings: Record<number, FindingOut[]>;
  placements: PlacementOut[];
  rows: ItemRowOut[];
  posted: { method: string; path: string; body: unknown }[];
}

export interface StubOptions {
  item?: Partial<ItemDetailOut>;
  findings?: FindingOut[];
  placements?: PlacementOut[];
  rows?: ItemRowOut[];
  /** Item history; defaults to the four-event fixture. */
  history?: ItemHistoryOut;
  /** Item attachments; defaults to the rate sheet. */
  attachments?: AttachmentOut[];
  /** Delay for POST /checks/preview, to capture the "checking" state. */
  previewDelayMs?: number;
}

const USERS: UserOut[] = [
  {
    ...REVIEWER,
    display_name: REVIEWER.name,
    email: 'reviewer@clearpath.demo',
    roles: ['reviewer'],
    is_active: true,
    is_available: true,
  },
  {
    ...MARKETER,
    display_name: MARKETER.name,
    email: 'marketer@clearpath.demo',
    roles: ['marketer'],
    is_active: true,
    is_available: true,
  },
];

/** A toy code-check engine: a few phrases with the real rules' messages, code-point spans. */
const PREVIEW_RULES: { phrase: string; draft: Omit<FindingDraftOut, 'span' | 'quote'> }[] = [
  {
    phrase: 'as low as',
    draft: {
      rule_id: 'pricing.as_low_as_range',
      citation: 'Reg Z 12 CFR 1026.24(a), 1026.16(a)',
      source: 'code',
      severity: 'blocking',
      message: 'Rate claim needs the full APR range',
      suggested_fix: 'Show the range: 5.99%–35.99% APR',
    },
  },
  {
    phrase: 'no impact on your credit score',
    draft: {
      rule_id: 'claims.credit_impact',
      citation: 'CFPB Supervisory Highlights Issue 24 §2.8.2; 12 U.S.C. 5536',
      source: 'code',
      severity: 'blocking',
      message: 'Credit-impact claim should be limited to checking your rate',
      suggested_fix: 'Checking your rate won’t affect your credit score.',
    },
  },
  {
    phrase: 'guaranteed',
    draft: {
      rule_id: 'claims.guaranteed',
      citation: '12 U.S.C. 5536; Reg Z 12 CFR 1026.24(a)',
      source: 'code',
      severity: 'blocking',
      message: '“Guaranteed” approval claims need a firm offer of credit',
      suggested_fix: 'Remove “guaranteed”',
    },
  },
];

function preview(body: CheckPreviewIn): CheckPreviewOut {
  const findings: FindingDraftOut[] = [];
  const lower = body.content_text.toLowerCase();
  for (const rule of PREVIEW_RULES) {
    const index = lower.indexOf(rule.phrase);
    if (index !== -1) {
      const quote = body.content_text.slice(index, index + rule.phrase.length);
      findings.push({ ...rule.draft, span: spanOf(body.content_text, quote), quote });
    }
  }
  if (body.markets.includes('CA') && !lower.includes('california financing law')) {
    findings.push({
      rule_id: 'ca.license_disclosure',
      citation: 'Cal. Fin. Code §22162',
      source: 'code',
      severity: 'blocking',
      message: 'California ads need the CFL license disclosure',
      suggested_fix: 'Add “Loans made or arranged pursuant to a California Financing Law license.”',
      span: null,
      quote: null,
    });
  }
  return { findings, terms_refs: [], ruleset_key: '2026-07-21:2026-10-24.3' };
}

/** A stand-in creative (kind `creative`), served as SVG so the review screen's mockup slot has something real. */
export const MOCKUP_ATTACHMENT: AttachmentOut = {
  ...ATTACHMENTS[0],
  id: 72,
  kind: 'creative',
  original_name: 'fall-pl-social-1080.svg',
  content_type: 'image/svg+xml',
  size_bytes: 1_204,
  download_url: '/api/attachments/72/download',
};

const MOCKUP_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="540" height="540" viewBox="0 0 540 540">
<rect width="540" height="540" fill="#f4f1ea"/><rect x="0" y="380" width="540" height="160" fill="#1f3a5f"/>
<text x="40" y="110" font-family="Georgia, serif" font-size="44" fill="#1f3a5f">Need cash fast?</text>
<text x="40" y="170" font-family="Helvetica, Arial" font-size="26" fill="#333">Personal loans as low as 5.99% APR</text>
<text x="40" y="215" font-family="Helvetica, Arial" font-size="20" fill="#555">Check your rate in 2 minutes</text>
<rect x="40" y="260" width="200" height="56" rx="6" fill="#e2a03f"/>
<text x="62" y="296" font-family="Helvetica, Arial" font-size="22" fill="#1f3a5f">Check my rate</text>
<text x="40" y="470" font-family="Helvetica, Arial" font-size="16" fill="#fff">ClearPath Financial · Loans from $2,000 to $40,000</text>
</svg>`;

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

export async function stubApi(page: Page, options: StubOptions = {}): Promise<StubState> {
  const item = itemFixture(options.item);
  const current = item.current_version_n ?? 1;
  const state: StubState = {
    item,
    findings: { [current]: structuredClone(options.findings ?? FINDINGS_OPEN) },
    placements: options.placements ?? (item.live_placements_count > 0 ? PLACEMENTS : []),
    rows: options.rows ?? [itemRowFixture(options.item)],
    posted: [],
  };
  const recount = () => {
    state.item.open_findings_count = (state.findings[current] ?? []).filter((f) => f.state === 'open').length;
  };
  const textOf = (n: number) =>
    n === current && state.item.current_version
      ? state.item.current_version.content_text
      : versionFixture(n === 1 ? 1 : 2).content_text;

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, '');
    const method = request.method();
    const body: unknown = method === 'GET' ? undefined : request.postDataJSON();
    if (method !== 'GET') state.posted.push({ method, path, body });

    let m: RegExpMatchArray | null;
    if (path === '/health') return json(route, { status: 'ok', database: true });
    if (path === '/users') return json(route, USERS);
    if (path === '/partners') return json(route, []);
    if (path === '/checks/preview') {
      if (options.previewDelayMs) await new Promise((r) => setTimeout(r, options.previewDelayMs));
      return json(route, preview(body as CheckPreviewIn));
    }
    if (path === '/items' && method === 'GET') return json(route, { rows: state.rows, next_cursor: null });
    if (path === '/items' && method === 'POST') {
      const data = body as SubmitItemIn;
      const created = itemFixture({
        id: 1077,
        key: 'CP-1077',
        title: data.title,
        status: 'submitted',
        round: 1,
        llm_check_status: 'pending',
        current_version: versionFixture(1, { content_text: data.content_text, terms_refs: [] }),
        current_version_n: 1,
        versions: [versionFixture(1)],
        assignee: null,
      });
      return json(route, created, 201);
    }
    if ((m = /^\/items\/\d+\/attachments$/.exec(path))) {
      return method === 'GET'
        ? json(route, options.attachments ?? ATTACHMENTS)
        : json(route, ATTACHMENTS[0], 201);
    }
    if (path === '/attachments/72/download') {
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: MOCKUP_SVG });
    }
    if ((m = /^\/items\/\d+$/.exec(path))) return json(route, state.item);
    if ((m = /^\/items\/\d+\/findings$/.exec(path))) {
      const n = Number(url.searchParams.get('version_n') ?? current);
      return json(route, state.findings[n] ?? []);
    }
    if ((m = /^\/findings\/(\d+)\/(accept|dismiss|reopen)$/.exec(path))) {
      const finding = (state.findings[current] ?? []).find((f) => f.id === Number(m?.[1]));
      if (finding === undefined)
        return json(route, { code: 'not_found', message: 'Finding not found.' }, 404);
      if (m[2] === 'accept')
        Object.assign(finding, { state: 'accepted', resolved_by: REVIEWER, resolved_at: NOW });
      if (m[2] === 'dismiss')
        Object.assign(finding, {
          state: 'dismissed',
          reason: (body as { reason: string }).reason,
          resolved_by: REVIEWER,
          resolved_at: NOW,
        });
      if (m[2] === 'reopen')
        Object.assign(finding, { state: 'open', reason: '', resolved_by: null, resolved_at: null });
      recount();
      return json(route, finding);
    }
    if ((m = /^\/items\/\d+\/decisions$/.exec(path))) {
      if (method === 'GET')
        return json(route, state.item.latest_decision ? [state.item.latest_decision] : []);
      const data = body as DecisionIn;
      const decision: DecisionOut = {
        id: 900,
        version_n: data.outcome === 'approved_with_edits' ? current + 1 : data.version_n,
        outcome: data.outcome,
        lane: 'standard',
        approver: REVIEWER,
        reason: data.reason,
        ruleset_date: '2026-07-21',
        expires_at: data.outcome.startsWith('approved') ? '2027-04-24T00:00:00Z' : null,
        llm_override_reason: data.llm_override_reason ?? null,
        ai_review_carried_from_n: null,
        terms_versions: [],
        evidence: [],
        decided_at: NOW,
      };
      state.item = {
        ...state.item,
        status: data.outcome === 'approved_with_edits' ? 'approved' : data.outcome,
        latest_decision: decision,
        approval_expires_at: decision.expires_at,
      };
      return json(route, decision, 201);
    }
    if ((m = /^\/items\/\d+\/llm-check\/retry$/.exec(path))) {
      state.item = { ...state.item, llm_check_status: 'running' };
      return json(route, itemRowFixture({ llm_check_status: 'running' }), 202);
    }
    if ((m = /^\/items\/\d+\/comments$/.exec(path))) return json(route, COMMENTS);
    if ((m = /^\/items\/\d+\/history$/.exec(path))) return json(route, options.history ?? HISTORY);
    if ((m = /^\/items\/\d+\/placements$/.exec(path))) return json(route, state.placements);
    if ((m = /^\/items\/\d+\/versions$/.exec(path))) return json(route, state.item.versions);
    if ((m = /^\/items\/\d+\/versions\/(\d+)$/.exec(path))) {
      const n = Number(m[1]);
      return json(route, {
        ...versionFixture(n === 1 ? 1 : 2),
        ...state.item.versions.find((v) => v.n === n),
        content_text: textOf(n),
      });
    }
    if ((m = /^\/items\/\d+\/diff$/.exec(path))) {
      const from = Number(url.searchParams.get('from_n'));
      const to = Number(url.searchParams.get('to_n'));
      return json(route, { from_n: from, to_n: to, segments: wordDiff(textOf(from), textOf(to)) });
    }
    return json(route, { code: 'not_found', message: `No stub for ${method} ${path}` }, 404);
  });
  return state;
}
