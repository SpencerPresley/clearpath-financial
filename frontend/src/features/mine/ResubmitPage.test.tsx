import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { CheckPreviewOut, ItemDetailOut, NewRoundIn, ResubmitIn } from '../../api/generated/model';
import {
  COPY_V2,
  DECISION_APPROVED,
  DECISION_CHANGES,
  FINDING_CREDIT,
  FINDING_QUALIFIER,
  FINDING_RATE,
  REVIEWER,
  itemFixture,
  versionFixture,
} from '../../test/fixtures/review';
import { reviewHandlers } from '../../test/fixtures/reviewHandlers';
import { server } from '../../test/server';
import { showToast } from '../../ui/toast';
import { ResubmitPage } from './ResubmitPage';
import { renderAtRoute } from '../../test/router';

vi.mock('../../ui/toast', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../ui/toast')>()),
  showToast: vi.fn(),
}));

const EDITED = COPY_V2.replace('5.99%', '6.49%');

const CHANGES_ITEM = itemFixture({
  status: 'changes_requested',
  latest_decision: { ...DECISION_CHANGES, version_n: 2 },
});

const FINDINGS = [
  { ...FINDING_RATE, state: 'accepted' as const, resolved_by: REVIEWER },
  { ...FINDING_CREDIT, state: 'dismissed' as const, reason: 'Limited in the footer.', resolved_by: REVIEWER },
  FINDING_QUALIFIER,
];

function previewHandler() {
  return http.post('*/api/checks/preview', () => {
    const out: CheckPreviewOut = { ruleset_key: 'k', terms_refs: [], findings: [] };
    return HttpResponse.json(out);
  });
}

async function renderResubmit(item: ItemDetailOut) {
  server.use(...reviewHandlers({ item, findings: FINDINGS }), previewHandler());
  const rendered = renderAtRoute(() => <ResubmitPage itemId={item.id} />, {
    path: '/mine/$itemId/resubmit',
    url: `/mine/${String(item.id)}/resubmit`,
  });
  await screen.findByRole('heading', { level: 1 });
  return rendered;
}

async function replaceCopy(user: ReturnType<typeof userEvent.setup>, text: string) {
  const editor = await screen.findByLabelText('Copy');
  await user.clear(editor);
  await user.click(editor);
  await user.paste(text);
}

beforeEach(() => {
  vi.mocked(showToast).mockClear();
});

describe('ResubmitPage', () => {
  it('prefills the current version and shows what was requested', async () => {
    await renderResubmit(CHANGES_ITEM);

    expect(await screen.findByLabelText('Copy')).toHaveValue(COPY_V2);
    const requested = screen.getByRole('region', { name: 'Requested changes' });
    expect(within(requested).getByText(/Add the California license line\./)).toBeInTheDocument();
    expect(within(requested).getByText(/Dana Reyes/)).toBeInTheDocument();
    // Accepted findings are the required changes; dismissed and open ones aren't.
    expect(await within(requested).findByText('Rate claim needs the full APR range')).toBeInTheDocument();
    expect(within(requested).queryByText(FINDING_CREDIT.message)).toBeNull();
    expect(within(requested).queryByText(FINDING_QUALIFIER.message)).toBeNull();
  });

  it('holds submit until the copy changes, then shows the edit in the diff', async () => {
    const user = userEvent.setup();
    await renderResubmit(CHANGES_ITEM);

    const submit = await screen.findByRole('button', { name: 'Resubmit' });
    expect(submit).toBeDisabled();
    expect(screen.getByText('No changes yet')).toBeInTheDocument();

    await replaceCopy(user, EDITED);
    expect(submit).toBeEnabled();

    await user.click(screen.getByRole('radio', { name: 'Changes vs v2' }));
    expect(screen.getByText('6.49').closest('ins')).not.toBeNull();
    expect(screen.getByText('5.99').closest('del')).not.toBeNull();
    expect(screen.getByText('1 change')).toBeInTheDocument();
  });

  it('resubmits after changes were requested, with the note', async () => {
    const bodies: ResubmitIn[] = [];
    server.use(
      http.post('*/api/items/:itemId/versions', async ({ request }) => {
        bodies.push((await request.json()) as ResubmitIn);
        return HttpResponse.json(versionFixture(2, { n: 3, content_text: EDITED }), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    const { router } = await renderResubmit(CHANGES_ITEM);

    await replaceCopy(user, EDITED);
    await user.type(screen.getByLabelText('What changed'), 'Raised the rate floor.');
    await user.click(screen.getByRole('button', { name: 'Resubmit' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1042');
    });
    expect(bodies).toEqual([{ content_text: EDITED, note: 'Raised the rate floor.' }]);
    expect(showToast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Resubmitted' }));
  });

  it('starts a new round for a withdrawn item, without a note', async () => {
    const bodies: NewRoundIn[] = [];
    server.use(
      http.post('*/api/items/:itemId/new-round', async ({ request }) => {
        bodies.push((await request.json()) as NewRoundIn);
        return HttpResponse.json(versionFixture(2, { n: 3, content_text: EDITED }), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    const { router } = await renderResubmit(
      itemFixture({ status: 'withdrawn', latest_decision: DECISION_APPROVED }),
    );

    expect(screen.queryByLabelText('What changed')).toBeNull();
    expect(screen.queryByRole('region', { name: 'Requested changes' })).toBeNull();
    await replaceCopy(user, EDITED);
    await user.click(screen.getByRole('button', { name: 'Start new round' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1042');
    });
    expect(bodies).toEqual([{ content_text: EDITED }]);
  });

  it('lets an expired approval run again with the same copy', async () => {
    const bodies: NewRoundIn[] = [];
    server.use(
      http.post('*/api/items/:itemId/new-round', async ({ request }) => {
        bodies.push((await request.json()) as NewRoundIn);
        return HttpResponse.json(versionFixture(2, { n: 3 }), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    await renderResubmit(itemFixture({ status: 'expired', latest_decision: DECISION_APPROVED }));

    const start = await screen.findByRole('button', { name: 'Start new round' });
    expect(start).toBeEnabled();
    await user.click(start);
    await waitFor(() => {
      expect(bodies).toEqual([{ content_text: COPY_V2 }]);
    });
  });

  it('explains instead of showing a form when there is nothing to resubmit', async () => {
    await renderResubmit(itemFixture({ status: 'in_review' }));
    expect(
      await screen.findByText(/CP-1042 is in review\. You can resubmit after a reviewer requests changes\./),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Copy')).toBeNull();
  });

  it('shows a server failure as one line and keeps the edit', async () => {
    server.use(
      http.post('*/api/items/:itemId/versions', () =>
        HttpResponse.json(
          { code: 'not_implemented', message: "Resubmitting isn't available yet." },
          { status: 501 },
        ),
      ),
    );
    const user = userEvent.setup();
    await renderResubmit(CHANGES_ITEM);

    await replaceCopy(user, EDITED);
    await user.click(screen.getByRole('button', { name: 'Resubmit' }));

    expect(await screen.findByText("Resubmitting isn't available yet.")).toBeInTheDocument();
    expect(screen.getByLabelText('Copy')).toHaveValue(EDITED);
  });
});
