import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryHistory, createRouter, RouterProvider } from '@tanstack/react-router';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { getHealthMockHandler } from '../../api/generated/core/core.msw';
import type { DecisionIn, FindingOut } from '../../api/generated/model';
import { getListUsersMockHandler } from '../../api/generated/users/users.msw';
import { routeTree } from '../../routeTree.gen';
import {
  DECISION_APPROVED,
  FINDINGS_OPEN,
  dismissedAll,
  FINDING_CREDIT,
  FINDING_RATE,
  REVIEWER,
  itemFixture,
  triaged,
  versionFixture,
} from '../../test/fixtures/review';
import { reviewHandlers } from '../../test/fixtures/reviewHandlers';
import type { ReviewHandlerOptions } from '../../test/fixtures/reviewHandlers';
import { server } from '../../test/server';
import type { Role } from '../../ui/domain';
import { ViewerProvider } from '../../ui/layout/Viewer';

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
    http.post('*/api/items/bulk/fast-track-approve', async ({ request }) => {
      posted.push({ path: new URL(request.url).pathname, body: await request.json() });
      return HttpResponse.json({ succeeded: [1042], skipped: [] });
    }),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [options.path ?? '/items/1042'] }),
    context: { queryClient },
  });
  const app = <RouterProvider router={router} />;
  render(
    <QueryClientProvider client={queryClient}>
      {options.roles === undefined ? (
        app
      ) : (
        <ViewerProvider viewer={{ name: 'T', roles: options.roles, isDemo: false }}>{app}</ViewerProvider>
      )}
    </QueryClientProvider>,
  );
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

describe('ReviewPage', () => {
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

  it('keeps plain Approve off while accepted findings need a change', async () => {
    renderReview({ findings: triaged(FINDINGS_OPEN) });
    expect(await screen.findByText('2 accepted findings need a change')).toBeInTheDocument();
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

  it('compares versions with a word diff', async () => {
    renderReview({ path: '/items/1042?compare=1' });
    expect(await screen.findByText(/Changes from v1 to v2/)).toBeInTheDocument();
    expect(document.querySelector('ins')?.textContent).toContain('Terms 24–60 months.');
  });

  it('offers fast-track, reaffirm, and pull on a re-review with a generated version', async () => {
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
    expect(screen.getByRole('button', { name: 'Reaffirm' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pull' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Fast-track approve v2' }));
    await userEvent.type(screen.getByLabelText(/^Reason/), 'Only the APR floor changed.');
    await userEvent.click(nthButton('Fast-track approve', -1));
    await waitFor(() => {
      expect(posted[0]).toEqual({
        path: '/api/items/bulk/fast-track-approve',
        body: { item_ids: [1042], reason: 'Only the APR floor changed.' },
      });
    });
  });

  it('does not offer fast-track when no version was generated', async () => {
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
