import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryHistory, createRouter, RouterProvider } from '@tanstack/react-router';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getHealthMockHandler } from '../../api/generated/core/core.msw';
import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import type {
  CommentOut,
  DecisionIn,
  FastTrackIn,
  FindingOut,
  ItemDetailOut,
} from '../../api/generated/model';
import { getListUsersMockHandler } from '../../api/generated/users/users.msw';
import { routeTree } from '../../routeTree.gen';
import {
  COMMENTS,
  DECISION_APPROVED,
  FINDINGS_OPEN,
  dismissedAll,
  FINDING_CREDIT,
  FINDING_QUALIFIER,
  FINDING_RATE,
  REVIEWER,
  itemFixture,
  triaged,
  versionFixture,
} from '../../test/fixtures/review';
import { reviewHandlers } from '../../test/fixtures/reviewHandlers';
import type { ReviewHandlerOptions } from '../../test/fixtures/reviewHandlers';
import { server } from '../../test/server';
import { ROLES } from '../../ui/domain';
import type { Role } from '../../ui/domain';
import { LLM_POLL_MS } from './useReviewData';

interface Posted {
  path: string;
  body: unknown;
}

/** Renders the real app at /items/1042 with the review fixtures; returns the list of writes. */
function renderReview(
  options: ReviewHandlerOptions & { path?: string; roles?: readonly Role[]; notFound?: boolean } = {},
) {
  const posted: Posted[] = [];
  const findings = [...(Array.isArray(options.findings) ? options.findings : FINDINGS_OPEN)];
  const respondFinding = (state: FindingOut['state']) =>
    http.post(
      `*/api/findings/:id/${state === 'accepted' ? 'accept' : state === 'dismissed' ? 'dismiss' : 'reopen'}`,
      async ({ request, params }) => {
        const body = state === 'open' ? {} : await request.json();
        posted.push({ path: new URL(request.url).pathname, body });
        const finding = findings.find((f) => f.id === Number(params.id)) ?? FINDING_RATE;
        return HttpResponse.json({
          ...finding,
          state,
          reason: state === 'dismissed' ? (body as { reason: string }).reason : '',
          resolved_by: state === 'open' ? null : REVIEWER,
          resolved_at: state === 'open' ? null : '2026-10-24T15:00:00Z',
        });
      },
    );
  server.use(
    ...(options.notFound === true
      ? [
          http.get('*/api/items/:id', () =>
            HttpResponse.json({ code: 'not_found', message: 'Not found.' }, { status: 404 }),
          ),
        ]
      : []),
    getHealthMockHandler({ status: 'ok', database: true }),
    getListUsersMockHandler([]),
    ...reviewHandlers({ ...options, findings }),
    respondFinding('accepted'),
    respondFinding('dismissed'),
    respondFinding('open'),
    http.post('*/api/items/:id/decisions', async ({ request }) => {
      const body = (await request.json()) as DecisionIn;
      posted.push({ path: new URL(request.url).pathname, body });
      return HttpResponse.json(
        { ...DECISION_APPROVED, outcome: body.outcome, reason: body.reason },
        { status: 201 },
      );
    }),
    http.post('*/api/items/:id/llm-check/retry', ({ request }) => {
      posted.push({ path: new URL(request.url).pathname, body: null });
      return HttpResponse.json({}, { status: 202 });
    }),
    http.post('*/api/items/:id/fast-track-approve', async ({ request }) => {
      const body = (await request.json()) as FastTrackIn;
      posted.push({ path: new URL(request.url).pathname, body });
      return HttpResponse.json(
        { ...DECISION_APPROVED, lane: 'fast_track', version_n: body.version_n, ai_review_carried_from_n: 1 },
        { status: 201 },
      );
    }),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [options.path ?? '/items/1042'] }),
    context: { queryClient },
  });
  const app = <RouterProvider router={router} />;
  // The root route resolves the viewer from GET /api/me (SessionGate); default to every role.
  const roles = options.roles ?? ROLES;
  server.use(
    getGetMeMockHandler({
      id: 1,
      display_name: 'T',
      email: 't@clearpath.demo',
      roles: [...roles],
      effective_roles: [...roles],
      is_available: true,
    }),
  );
  render(<QueryClientProvider client={queryClient}>{app}</QueryClientProvider>);
  return { posted, router };
}

/** The nth button with this exact name (the bar's Approve is first, the panel's submit second). */
function nthButton(name: string, index: number): HTMLElement {
  const buttons = screen.getAllByRole('button', { name });
  const button = index < 0 ? buttons[buttons.length + index] : buttons[index];
  if (button === undefined) throw new Error(`No button ${String(index)} named ${name}`);
  return button;
}
const approveButton = () => nthButton('Approve', 0);
const COMMENT_301 = 'Footer disclosure looks right now. Waiting on the APR range.';

describe('ReviewPage', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows a skeleton, then the item with its flagged spans', async () => {
    renderReview();
    expect(await screen.findByRole('status', { name: 'Loading item' })).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { name: 'Fall personal loan promo — paid social' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(document.querySelector('mark[data-mark-ids~="9003"]')).not.toBeNull();
    });
    const mark = document.querySelector('mark[data-mark-ids~="9003"]');
    expect(mark?.textContent).toBe('no impact on your credit score');
    expect(mark).toHaveAttribute('data-severity', 'blocking');
  });

  it('disables Approve with the reason until every finding is triaged', async () => {
    renderReview({ findings: [FINDING_RATE, FINDING_CREDIT] });
    await screen.findByText('2 findings to triage');
    expect(approveButton()).toBeDisabled();
  });

  it('moves through findings with n and p and accepts with a', async () => {
    const { posted } = renderReview();
    await screen.findByText('4 findings to triage');
    await userEvent.keyboard('n');
    expect(document.getElementById('finding-9001')).toHaveAttribute('aria-current', 'true');
    await userEvent.keyboard('n');
    expect(document.getElementById('finding-9003')).toHaveAttribute('aria-current', 'true');
    await userEvent.keyboard('p');
    expect(document.getElementById('finding-9001')).toHaveAttribute('aria-current', 'true');
    await userEvent.keyboard('a');
    await waitFor(() => {
      expect(posted.map((p) => p.path)).toContain('/api/findings/9001/accept');
    });
    expect(await screen.findByText(/Accepted by Dana Reyes/)).toBeInTheDocument();
  });

  it('dismisses with a required reason, and typing the reason never triggers shortcuts', async () => {
    const { posted } = renderReview();
    await screen.findByText('4 findings to triage');
    await userEvent.keyboard('n');
    await userEvent.keyboard('d');
    const reason = screen.getByLabelText('Reason for dismissing');
    expect(reason).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    expect(screen.getByText('Say why this finding doesn’t apply.')).toBeInTheDocument();
    await userEvent.type(reason, 'and dad');
    await userEvent.keyboard('{Enter}');
    await waitFor(() => {
      expect(posted).toEqual([{ path: '/api/findings/9001/dismiss', body: { reason: 'and dad' } }]);
    });
  });

  it('labels carried dismissals', async () => {
    renderReview({
      findings: [
        {
          ...FINDING_RATE,
          state: 'dismissed',
          reason: 'Range is in the footer.',
          carried_from_id: 8001,
          resolved_by: REVIEWER,
          resolved_at: '2026-10-24T10:00:00Z',
        },
      ],
    });
    expect(await screen.findByText(/Dismissal carried from an earlier version/)).toBeInTheDocument();
    expect(screen.getByText('Range is in the footer.')).toBeInTheDocument();
  });

  it('labels AI findings as suggestions with their citation', async () => {
    renderReview();
    const card = await screen.findByRole('article', { name: /creditworthiness qualifier/ });
    expect(within(card).getByText('AI suggestion')).toBeInTheDocument();
    expect(within(card).getByText(/CFPB Supervisory Highlights Issue 24/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/violation/i);
  });

  it('approves once everything is dismissed, posting the reason and evidence', async () => {
    const { posted } = renderReview({ findings: dismissedAll(FINDINGS_OPEN) });
    await screen.findByRole('heading', { name: /Fall personal loan/ });
    await waitFor(() => {
      expect(approveButton()).toBeEnabled();
    });
    await userEvent.click(approveButton());
    await userEvent.type(screen.getByLabelText(/^Reason/), 'Range present.');
    await userEvent.click(nthButton('Approve', 1));
    await waitFor(() => {
      expect(posted[0]).toEqual({
        path: '/api/items/1042/decisions',
        body: {
          outcome: 'approved',
          version_n: 2,
          reason: 'Range present.',
          evidence_attachment_ids: [71],
          llm_override_reason: null,
          edited_content_text: null,
        },
      });
    });
  });

  it('blocks Approve while the AI check runs', async () => {
    renderReview({ item: itemFixture({ llm_check_status: 'running' }), findings: triaged(FINDINGS_OPEN) });
    expect(await screen.findByText('AI check running')).toBeInTheDocument();
    expect(screen.getByText(/AI check running…/)).toBeInTheDocument();
    expect(approveButton()).toBeDisabled();
  });

  it('polls while the AI check runs, then shows its findings and stops polling', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const running = itemFixture({ llm_check_status: 'running' });
    const done = itemFixture({ llm_check_status: 'succeeded' });
    const before = dismissedAll([FINDING_RATE, FINDING_CREDIT]);
    let finished = false;
    let itemGets = 0;
    renderReview({ item: running, findings: before });
    server.use(
      http.get('*/api/items/:id', () => {
        itemGets += 1;
        return HttpResponse.json(finished ? done : running);
      }),
      http.get('*/api/items/:itemId/findings', () =>
        HttpResponse.json(finished ? [...before, FINDING_QUALIFIER] : before),
      ),
    );
    expect(await screen.findByText(/AI check running…/)).toBeInTheDocument();
    expect(approveButton()).toBeDisabled();

    finished = true;
    await vi.advanceTimersByTimeAsync(LLM_POLL_MS);

    expect(await screen.findByText('AI check finished · 1 suggestion')).toBeInTheDocument();
    expect(await screen.findByRole('article', { name: /creditworthiness qualifier/ })).toBeInTheDocument();
    const settled = itemGets;
    await vi.advanceTimersByTimeAsync(LLM_POLL_MS * 2);
    expect(itemGets).toBe(settled);
  });

  it('requires an override reason to approve after the AI check failed, and offers Retry', async () => {
    const { posted } = renderReview({
      item: itemFixture({ llm_check_status: 'failed' }),
      findings: dismissedAll(FINDINGS_OPEN),
    });
    await screen.findByText('AI check failed.');
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => {
      expect(posted.map((p) => p.path)).toContain('/api/items/1042/llm-check/retry');
    });
    await userEvent.click(approveButton());
    await userEvent.type(screen.getByLabelText(/^Reason/), 'Checked by hand.');
    await userEvent.click(nthButton('Approve', 1));
    expect(screen.getByText('Say why it’s safe to approve without the AI check.')).toBeInTheDocument();
    await userEvent.type(
      screen.getByLabelText(/^Override reason/),
      'Vendor outage; copy reviewed line by line.',
    );
    await userEvent.click(nthButton('Approve', 1));
    await waitFor(() => {
      expect(posted.at(-1)?.body).toMatchObject({
        llm_override_reason: 'Vendor outage; copy reviewed line by line.',
      });
    });
  });

  it('shows why the AI check failed, with Retry', async () => {
    renderReview({
      item: itemFixture({
        llm_check_status: 'failed',
        llm_check_failure_code: 'provider_unavailable',
        llm_check_failure_reason:
          "The AI service didn't answer after 4 tries. Couldn't reach the model provider.",
      }),
      findings: dismissedAll(FINDINGS_OPEN),
    });
    const status = (await screen.findByText(/AI check failed:/)).closest('.app-llm-status');
    expect(status).toHaveTextContent(
      "AI check failed: The AI service didn't answer after 4 tries. Couldn't reach the model provider.",
    );
    expect(within(status as HTMLElement).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('says plainly when AI review is not configured, and offers no Retry', async () => {
    renderReview({
      item: itemFixture({
        llm_check_status: 'failed',
        llm_check_failure_code: 'not_configured',
        llm_check_failure_reason: "The AI check didn't run: no Anthropic API key is configured here.",
      }),
      findings: dismissedAll(FINDINGS_OPEN),
    });
    const status = (await screen.findByText(/AI review isn’t configured on this server\./)).closest(
      '.app-llm-status',
    );
    expect(status).toHaveTextContent('Give an override reason when you approve.');
    expect(within(status as HTMLElement).queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('keeps plain Approve off while accepted findings need a change', async () => {
    renderReview({ findings: triaged(FINDINGS_OPEN) });
    // The note names the way forward, under the buttons.
    expect(
      await screen.findByText('2 accepted findings need a change · Approve with edits or Request changes'),
    ).toBeInTheDocument();
    expect(approveButton()).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Approve with edits' })).toBeEnabled();
  });

  it('reloads and returns to triage when the edited version comes back with new findings', async () => {
    const { posted } = renderReview({ findings: triaged(FINDINGS_OPEN) });
    server.use(
      http.post('*/api/items/:id/decisions', async ({ request }) => {
        posted.push({ path: new URL(request.url).pathname, body: await request.json() });
        return HttpResponse.json(
          { code: 'findings_need_triage', message: 'v3 has 1 new finding. Triage it, then approve again.' },
          { status: 409 },
        );
      }),
    );
    await screen.findByRole('heading', { name: /Fall personal loan/ });
    await userEvent.keyboard('e');
    await userEvent.type(await screen.findByLabelText('Edited copy (v3)'), ' Guaranteed.');
    await userEvent.type(screen.getByLabelText(/^Reason/), 'Tightened the claim.');
    await userEvent.click(screen.getByRole('button', { name: 'Approve edited version' }));
    expect(
      await screen.findByText('v3 has 1 new finding. Triage it, then approve again.'),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Edited copy (v3)')).not.toBeInTheDocument();
  });

  it('submits the open decision with Mod+Enter from the reason field', async () => {
    const { posted } = renderReview({ findings: dismissedAll(FINDINGS_OPEN) });
    await screen.findByRole('heading', { name: /Fall personal loan/ });
    await userEvent.click(approveButton());
    await userEvent.type(screen.getByLabelText(/^Reason/), 'All clear.');
    await userEvent.keyboard('{Control>}{Enter}{/Control}');
    await waitFor(() => {
      expect(posted[0]?.body).toMatchObject({ outcome: 'approved', reason: 'All clear.' });
    });
  });

  it('re-approves a reviewer-edit version without sending text again', async () => {
    const { posted } = renderReview({
      item: itemFixture({ current_version: versionFixture(2, { origin: 'reviewer_edit' }) }),
      findings: dismissedAll(FINDINGS_OPEN),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Approve with edits' }));
    expect(screen.getByRole('heading', { name: 'Approve your edited v2' })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Edited copy/)).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/^Reason/), 'Edit triaged.');
    await userEvent.click(screen.getByRole('button', { name: 'Approve edited version' }));
    await waitFor(() => {
      expect(posted[0]?.body).toMatchObject({
        outcome: 'approved_with_edits',
        version_n: 2,
        edited_content_text: null,
      });
    });
  });

  it('prefills Request changes from accepted findings', async () => {
    renderReview({ findings: triaged(FINDINGS_OPEN) });
    await userEvent.click(await screen.findByRole('button', { name: 'Request changes' }));
    expect(screen.getByLabelText(/^Changes needed/)).toHaveValue(
      '- Rate claim needs the full APR range (“as low as 5.99% APR”)\n- “As low as” may need a creditworthiness qualifier (“as low as”)',
    );
  });

  it('confirms before rejecting', async () => {
    const { posted } = renderReview();
    await userEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    await userEvent.type(screen.getByLabelText(/^Reason/), 'Prohibited claim.');
    await userEvent.click(screen.getByRole('button', { name: 'Reject…' }));
    const dialog = await screen.findByRole('alertdialog', { name: 'Reject CP-1042?' });
    expect(posted).toEqual([]);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Reject CP-1042' }));
    await waitFor(() => {
      expect(posted[0]?.body).toMatchObject({ outcome: 'rejected', reason: 'Prohibited claim.' });
    });
  });

  it('approves with edits by posting the reviewer-authored text', async () => {
    const { posted } = renderReview({ findings: triaged(FINDINGS_OPEN) });
    await screen.findByRole('heading', { name: /Fall personal loan/ });
    await userEvent.keyboard('e');
    await screen.findByRole('heading', { name: 'Approve with edits as v3' });
    const editor = await screen.findByLabelText('Edited copy (v3)');
    expect(screen.getByRole('button', { name: 'Approve edited version' })).toBeDisabled();
    await userEvent.type(editor, ' Rates 5.99%–35.99% APR.');
    await userEvent.type(screen.getByLabelText(/^Reason/), 'Added the range.');
    await userEvent.click(screen.getByRole('button', { name: 'Approve edited version' }));
    await waitFor(() => {
      expect(posted[0]?.body).toMatchObject({
        outcome: 'approved_with_edits',
        edited_content_text: `${versionFixture(2).content_text} Rates 5.99%–35.99% APR.`,
      });
    });
  });

  it('shows an older version read-only and says where decisions apply', async () => {
    renderReview({ path: '/items/1042?v=1' });
    expect(
      await screen.findByText(/Viewing v1\. Findings are read-only here; decisions apply to v2\./),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
  });

  it('brings a linked comment into view: focused and marked (?comment=)', async () => {
    renderReview({ path: '/items/1042?tab=comments&v=2&comment=301' });

    const body = await screen.findByText('Footer disclosure looks right now. Waiting on the APR range.');
    const comment = body.closest('li');
    await waitFor(() => {
      expect(comment).toHaveFocus();
    });
    expect(comment).toHaveAttribute('data-linked', 'true');
    expect(comment).toHaveAttribute('aria-current', 'true');
  });

  it('brings a linked comment into view once, not on every return to Comments', async () => {
    const user = userEvent.setup();
    renderReview({ path: '/items/1042?tab=comments&v=2&comment=301' });
    const first = (await screen.findByText(COMMENT_301)).closest('li');
    await waitFor(() => {
      expect(first).toHaveFocus();
    });

    await user.click(screen.getByRole('tab', { name: /Findings/ }));
    await user.click(screen.getByRole('tab', { name: /Comments/ }));

    const again = (await screen.findByText(COMMENT_301)).closest('li');
    expect(again).not.toHaveFocus();
    expect(again).not.toHaveAttribute('data-linked');
    expect(again).toHaveAttribute('aria-current', 'true');
  });

  it('brings a second link on the same page into view (a new mention while Comments is open)', async () => {
    const reply = { ...COMMENTS[0], id: 302, body: 'APR range added in the footer.' } as CommentOut;
    const { router } = renderReview({
      path: '/items/1042?tab=comments&v=2&comment=301',
      comments: [...COMMENTS, reply],
    });
    const first = (await screen.findByText(COMMENT_301)).closest('li');
    await waitFor(() => {
      expect(first).toHaveFocus();
    });

    await router.navigate({ to: '.', search: (prev) => ({ ...prev, comment: 302 }) });

    const second = screen.getByText('APR range added in the footer.').closest('li');
    await waitFor(() => {
      expect(second).toHaveFocus();
    });
    expect(second).toHaveAttribute('data-linked', 'true');
    expect(first).not.toHaveAttribute('data-linked');
  });

  it('ignores a linked comment that is not on the version shown', async () => {
    renderReview({ path: '/items/1042?tab=comments&v=2&comment=999' });

    await screen.findByText('Footer disclosure looks right now. Waiting on the APR range.');
    expect(document.querySelector('[data-linked]')).toBeNull();
  });

  it("links the partner on the Details tab to the partner's page (agreement and evidence)", async () => {
    renderReview({
      path: '/items/1042?tab=details',
      item: itemFixture({ partner: { id: 7, name: 'LoanFinder' } }),
    });
    expect(await screen.findByRole('link', { name: 'LoanFinder' })).toHaveAttribute('href', '/partners/7');
  });

  it('compares versions with a word diff', async () => {
    renderReview({ path: '/items/1042?compare=1' });
    expect(await screen.findByText(/Changes from v1 to v2/)).toBeInTheDocument();
    expect(document.querySelector('ins')?.textContent).toContain('Terms 24–60 months.');
  });

  it('offers fast-track and pull, not reaffirm, when terms changed and a version was generated', async () => {
    const { posted } = renderReview({
      item: itemFixture({
        status: 'needs_rereview',
        reopen_reason: 'terms_changed',
        llm_check_status: 'skipped',
        live_placements_count: 1,
        latest_decision: { ...DECISION_APPROVED, version_n: 1 },
        current_version: versionFixture(2, { origin: 'fast_track' }),
      }),
      findings: [],
    });
    expect(await screen.findByText(/Re-review: Offer terms changed\./)).toBeInTheDocument();
    expect(screen.getByText('AI review carried from v1')).toBeInTheDocument();
    // Reaffirm would re-check v1 against the new terms and be refused (reviews/decisions.py reaffirm).
    expect(screen.queryByRole('button', { name: /Reaffirm/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pull' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Fast-track approve v2' }));
    await userEvent.type(screen.getByLabelText(/^Reason/), 'Only the APR floor changed.');
    await userEvent.click(nthButton('Fast-track approve', -1));
    await waitFor(() => {
      // The single endpoint, at the version on screen: never a version that arrived after the page loaded.
      expect(posted[0]).toEqual({
        path: '/api/items/1042/fast-track-approve',
        body: { version_n: 2, reason: 'Only the APR floor changed.' },
      });
    });
  });

  it('reloads and says so when a newer version arrived before the fast-track click', async () => {
    const shown = itemFixture({
      status: 'needs_rereview',
      reopen_reason: 'terms_changed',
      llm_check_status: 'skipped',
      latest_decision: { ...DECISION_APPROVED, version_n: 1 },
      current_version: versionFixture(2, { origin: 'fast_track' }),
    });
    const newer: ItemDetailOut = {
      ...shown,
      current_version_n: 3,
      current_version: versionFixture(2, { n: 3, id: 503, origin: 'fast_track' }),
    };
    let stale = false;
    const { posted } = renderReview({ item: shown, findings: [] });
    server.use(
      http.get('*/api/items/:id', () => HttpResponse.json(stale ? newer : shown)),
      http.post('*/api/items/:id/fast-track-approve', async ({ request }) => {
        posted.push({ path: new URL(request.url).pathname, body: await request.json() });
        stale = true;
        return HttpResponse.json(
          {
            code: 'stale_version',
            message: "v2 isn't the current version (v3). Reload the item.",
            details: { version_n: 2, current_n: 3 },
          },
          { status: 409 },
        );
      }),
    );
    await userEvent.click(await screen.findByRole('button', { name: 'Fast-track approve v2' }));
    await userEvent.type(screen.getByLabelText(/^Reason/), 'Only the APR floor changed.');
    await userEvent.click(nthButton('Fast-track approve', -1));
    expect(
      await screen.findByText(
        'A newer version, v3, arrived while you had this open. Check it, then fast-track again.',
      ),
    ).toBeInTheDocument();
    // The item was reloaded: the panel now offers v3, the version now on screen.
    expect(await screen.findByRole('heading', { name: 'Fast-track approve v3' })).toBeInTheDocument();
    expect(posted.map((p) => p.body)).toEqual([{ version_n: 2, reason: 'Only the APR floor changed.' }]);
  });

  it('labels a terms re-review whose numbers did not change, so fast-track reads as a confirmation', async () => {
    renderReview({
      item: itemFixture({
        status: 'needs_rereview',
        reopen_reason: 'terms_changed',
        llm_check_status: 'skipped',
        live_placements_count: 1,
        latest_decision: { ...DECISION_APPROVED, version_n: 1 },
        current_version: versionFixture(2, {
          origin: 'fast_track',
          content_text: versionFixture(1).content_text,
        }),
        numbers_change: false,
      }),
      findings: [],
    });
    const label = await screen.findByText('Numbers unchanged.');
    const note = label.closest('.app-note');
    expect(note).toHaveTextContent('v2 matches approved v1; fast-track confirms it against the new terms.');
    // Nothing to compare: the diff would be empty.
    expect(screen.queryByRole('button', { name: /Compare with approved/ })).not.toBeInTheDocument();
    expect(screen.getByText('AI review carried from v1').closest('.app-llm-status')).toHaveTextContent(
      'numbers unchanged',
    );
  });

  it('offers reaffirm and pull, not fast-track, when the approval expired', async () => {
    renderReview({
      item: itemFixture({
        status: 'needs_rereview',
        reopen_reason: 'approval_expired',
        latest_decision: DECISION_APPROVED,
      }),
      findings: [],
    });
    await screen.findByText(/Re-review: Approval expired\./);
    expect(screen.queryByRole('button', { name: /Fast-track/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reaffirm v2' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pull' })).toBeInTheDocument();
  });

  it('offers Check now, not reaffirm, while the partner page still differs', async () => {
    const { posted, router } = renderReview({
      item: itemFixture({
        status: 'needs_rereview',
        reopen_reason: 'drift_detected',
        latest_decision: DECISION_APPROVED,
        drift_rereview: { placement_id: 3, restored: false },
      }),
      findings: [],
    });
    server.use(
      http.post('*/api/placements/:id/drift-checks', ({ request }) => {
        posted.push({ path: new URL(request.url).pathname, body: null });
        return HttpResponse.json({}, { status: 202 });
      }),
    );
    const label = await screen.findByText(/Re-review: Live copy changed\./);
    expect(label.closest('.app-note')).toHaveTextContent(
      'The partner page doesn’t show approved v2. Check it again once the partner restores it, or pull it.',
    );
    expect(screen.queryByRole('button', { name: /Reaffirm/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pull' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Check now' }));

    await waitFor(() => {
      expect(posted.map((p) => p.path)).toContain('/api/placements/3/drift-checks');
    });
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ tab: 'details' });
    });
  });

  it('offers reaffirm once a check found the copy restored', async () => {
    renderReview({
      item: itemFixture({
        status: 'needs_rereview',
        reopen_reason: 'drift_detected',
        latest_decision: DECISION_APPROVED,
        drift_rereview: { placement_id: 3, restored: true },
      }),
      findings: [],
    });
    const label = await screen.findByText(/Re-review: Live copy changed\./);
    expect(label.closest('.app-note')).toHaveTextContent(
      'A check found approved v2 on the partner page again.',
    );
    expect(screen.getByRole('button', { name: 'Reaffirm v2' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Check now' })).not.toBeInTheDocument();
  });

  it('sends a terms change with no generated version to the normal lane', async () => {
    const { posted } = renderReview({
      item: itemFixture({
        status: 'needs_rereview',
        reopen_reason: 'terms_changed',
        latest_decision: DECISION_APPROVED,
      }),
      findings: [],
    });
    server.use(
      http.post('*/api/items/:id/claim', ({ request }) => {
        posted.push({ path: new URL(request.url).pathname, body: null });
        return HttpResponse.json({});
      }),
    );
    expect(await screen.findByText(/no updated version could be generated/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Reaffirm|Fast-track|Claim/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pull' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));
    await waitFor(() => {
      expect(posted.map((p) => p.path)).toContain('/api/items/1042/claim');
    });
  });

  it('explains a withdrawn item', async () => {
    renderReview({ item: itemFixture({ status: 'withdrawn' }), findings: [] });
    expect(await screen.findByText(/The marketer can start a new round/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
  });

  it('offers Claim on an unassigned item', async () => {
    const { posted } = renderReview({ item: itemFixture({ status: 'submitted', assignee: null }) });
    server.use(
      http.post('*/api/items/:id/claim', ({ request }) => {
        posted.push({ path: new URL(request.url).pathname, body: null });
        return HttpResponse.json({});
      }),
    );
    await userEvent.click(await screen.findByRole('button', { name: 'Claim' }));
    await waitFor(() => {
      expect(posted.map((p) => p.path)).toContain('/api/items/1042/claim');
    });
  });

  it('hides decisions and triage from marketers', async () => {
    renderReview({ roles: ['marketer'] });
    await screen.findByRole('heading', { name: /Fall personal loan/ });
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Accept' })).not.toBeInTheDocument();
  });

  it('says when the item does not exist', async () => {
    renderReview({ path: '/items/9', notFound: true });
    expect(await screen.findByText('CP-9 not found')).toBeInTheDocument();
  });
});
