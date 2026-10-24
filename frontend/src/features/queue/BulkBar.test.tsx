import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getBulkFastTrackApproveMockHandler } from '../../api/generated/decisions/decisions.msw';
import { getBulkAssignItemsMockHandler } from '../../api/generated/items/items.msw';
import type { BulkAssignIn, BulkFastTrackIn } from '../../api/generated/model';
import { getListUsersMockHandler } from '../../api/generated/users/users.msw';
import { server } from '../../test/server';
import { renderWithQuery } from '../../test/render';
import type { Viewer } from '../../ui/layout/Viewer';
import { ToastHost } from '../../ui/toast';
import { BulkBar } from './BulkBar';
import { makeRow, USERS } from './fixtures';

const LEAD: Viewer = { id: 4, name: 'Priya Raman', email: 'lead@x', roles: ['lead', 'reviewer'] };
const REVIEWER: Viewer = { id: 2, name: 'Dana Whitfield', email: 'dana@x', roles: ['reviewer'] };

const ROWS = [
  makeRow({ id: 1, status: 'submitted' }),
  makeRow({ id: 2, status: 'in_review' }),
  makeRow({ id: 3, status: 'needs_rereview', reopen_reason: 'terms_changed', current_version_n: 4 }),
];

function setup(viewer: Viewer, selectedIds = [1, 2, 3], rows = ROWS) {
  const onSelectionChange = vi.fn();
  renderWithQuery(
    <>
      <BulkBar viewer={viewer} selectedIds={selectedIds} rows={rows} onSelectionChange={onSelectionChange} />
      <ToastHost />
    </>,
  );
  return { onSelectionChange };
}

beforeEach(() => {
  server.use(getListUsersMockHandler(USERS));
});

describe('BulkBar', () => {
  it('turns fast-track off, and says why, when no selected re-review can take it (nit 16)', () => {
    const expiry = makeRow({ id: 16, status: 'needs_rereview', reopen_reason: 'approval_expired' });
    setup(LEAD, [1, 16], [ROWS[0] ?? expiry, expiry]);
    const button = screen.getByRole('button', { name: 'Fast-track' });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(
      'Only offer-terms re-reviews can be fast-tracked, and none is selected.',
    );
    // The reason is also on a trigger of its own (a disabled button gets no hover).
    expect(screen.getByRole('button', { name: 'Why fast-track is off' })).toBeInTheDocument();
  });

  it('keeps fast-track on when one selected re-review qualifies', () => {
    const expiry = makeRow({ id: 16, status: 'needs_rereview', reopen_reason: 'approval_expired' });
    setup(LEAD, [3, 16], [...ROWS, expiry]);
    expect(screen.getByRole('button', { name: 'Fast-track 2 re-reviews…' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Why fast-track is off' })).not.toBeInTheDocument();
  });

  it('assigns the selection to a reviewer and clears it', async () => {
    const bodies: BulkAssignIn[] = [];
    server.use(
      getBulkAssignItemsMockHandler(async ({ request }) => {
        bodies.push((await request.json()) as BulkAssignIn);
        return { succeeded: [1, 2, 3], skipped: [] };
      }),
    );
    const { onSelectionChange } = setup(LEAD);
    expect(screen.getByText('3 selected')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Assign…' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Sam Okafor' }));

    await waitFor(() => {
      expect(bodies).toEqual([{ item_ids: [1, 2, 3], assignee_id: 3 }]);
    });
    expect(await screen.findByText('Assigned 3 items to Sam Okafor')).toBeInTheDocument();
    expect(onSelectionChange).toHaveBeenLastCalledWith([]);
  });

  it('keeps skipped items selected and reports them', async () => {
    server.use(
      getBulkAssignItemsMockHandler({
        succeeded: [1, 2],
        skipped: [{ item_id: 3, code: 'invalid_transition', message: 'CP-3 is already decided.' }],
      }),
    );
    const { onSelectionChange } = setup(LEAD);
    await userEvent.click(screen.getByRole('button', { name: 'Assign…' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Unassigned' }));

    expect(await screen.findByText('Assigned 2 of 3 items · 1 skipped')).toBeInTheDocument();
    expect(screen.getByText('CP-3 is already decided.')).toBeInTheDocument();
    expect(onSelectionChange).toHaveBeenLastCalledWith([3]);
  });

  it('shows the server message when the action is not available yet', async () => {
    server.use(
      http.post('*/api/items/bulk/assign', () =>
        HttpResponse.json(
          { code: 'not_implemented', message: 'Bulk assignment is not available yet.' },
          { status: 501 },
        ),
      ),
    );
    setup(LEAD);
    await userEvent.click(screen.getByRole('button', { name: 'Assign…' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Dana Whitfield' }));
    expect(await screen.findByText('Bulk assignment is not available yet.')).toBeInTheDocument();
  });

  it('gives reviewers no bulk assign (leads and admins only)', () => {
    setup(REVIEWER);
    expect(screen.queryByRole('button', { name: 'Assign…' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Fast-track/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Clear selection' })).toBeInTheDocument();
  });

  it('hides fast-track unless a re-review item is selected', () => {
    setup(LEAD, [1, 2]);
    expect(screen.queryByRole('button', { name: /Fast-track/ })).toBeNull();
  });

  it('fast-tracks only the re-review items, at the versions the rows showed, with a required reason', async () => {
    const bodies: BulkFastTrackIn[] = [];
    server.use(
      getBulkFastTrackApproveMockHandler(async ({ request }) => {
        bodies.push((await request.json()) as BulkFastTrackIn);
        return { succeeded: [3], skipped: [] };
      }),
    );
    setup(LEAD);
    await userEvent.click(screen.getByRole('button', { name: 'Fast-track 1 re-review…' }));
    const confirm = await screen.findByRole('button', { name: 'Fast-track approve' });
    expect(confirm).toBeDisabled();
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Reason' }),
      'Only the APR changed (terms v13).',
    );
    await userEvent.click(confirm);
    await waitFor(() => {
      expect(bodies).toEqual([
        {
          item_ids: [3],
          reason: 'Only the APR changed (terms v13).',
          // A version generated after the queue loaded is skipped (stale_version), not approved unseen.
          seen_versions: [{ item_id: 3, version_n: 4 }],
        },
      ]);
    });
    expect(await screen.findByText('Fast-tracked 1 item')).toBeInTheDocument();
  });
});
