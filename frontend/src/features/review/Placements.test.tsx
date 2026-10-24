import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import type { ItemDriftOut, PlacementDriftOut, SnapshotOut } from '../../api/generated/model';
import type { Role } from '../../ui/domain';
import { ViewerProvider } from '../../ui/layout/Viewer';
import { renderWithQuery } from '../../test/render';
import { server } from '../../test/server';
import { checkOutcome, PlacementsSection } from './Placements';

const NOW = '2026-10-24T15:00:00Z';
const OWNER_ID = 11;

function snapshot(overrides: Partial<SnapshotOut> = {}): SnapshotOut {
  return {
    id: 7,
    placement_id: 3,
    status: 'succeeded',
    trigger: 'scheduled',
    requested_by: null,
    requested_at: NOW,
    finished_at: NOW,
    url: 'https://lendcompare.example/best-loans',
    final_url: 'https://lendcompare.example/best-loans',
    http_status: 200,
    title: 'Best loans',
    compared_version_n: 1,
    result: 'unchanged',
    score: 100,
    diff: [],
    findings: [],
    new_blocking_count: 0,
    error_code: null,
    error_message: null,
    reopened_item: false,
    ...overrides,
  };
}

function placement(overrides: Partial<PlacementDriftOut> = {}): PlacementDriftOut {
  return {
    placement_id: 3,
    location: 'LendCompare: best personal loans',
    url: 'https://lendcompare.example/best-loans',
    monitored: true,
    is_live: true,
    latest: snapshot(),
    gone_streak: 0,
    demo_page: null,
    ...overrides,
  };
}

function serve(...responses: ItemDriftOut[]): { gets: () => number } {
  let count = 0;
  server.use(
    http.get('*/api/items/:id/drift', () => {
      const body = responses[Math.min(count, responses.length - 1)];
      count += 1;
      return HttpResponse.json(body);
    }),
  );
  return { gets: () => count };
}

function renderSection(roles: Role[] = ['reviewer'], viewerId = 99) {
  return renderWithQuery(
    <ViewerProvider viewer={{ id: viewerId, name: 'Viewer', email: 'v@clearpath.demo', roles }}>
      <PlacementsSection itemId={1042} ownerId={OWNER_ID} />
    </ViewerProvider>,
  );
}

describe('checkOutcome', () => {
  it('names every state with a tone and a glyph', () => {
    expect(checkOutcome(snapshot())).toEqual({
      label: 'Unchanged',
      tone: 'success',
      icon: 'drift.unchanged',
    });
    expect(checkOutcome(snapshot({ result: 'modified' })).tone).toBe('alert');
    expect(checkOutcome(snapshot({ result: 'missing' })).label).toBe('Copy missing');
    expect(checkOutcome(snapshot({ status: 'failed', result: null })).label).toBe('Check failed');
    expect(checkOutcome(snapshot({ status: 'pending', result: null })).label).toBe('Checking the page…');
  });

  it('reads a failed check that reopened the item as the copy missing', () => {
    expect(checkOutcome(snapshot({ status: 'failed', result: null, reopened_item: true }))).toEqual({
      label: 'Page not found',
      tone: 'alert',
      icon: 'drift.missing',
    });
  });
});

describe('PlacementsSection', () => {
  it('shows an unchanged daily check', async () => {
    serve({ item_id: 1042, placements: [placement()] });
    renderSection();

    expect(await screen.findByText('Unchanged')).toBeInTheDocument();
    expect(screen.getByText(/Daily check against v1/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /lendcompare\.example\/best-loans/ })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    );
    expect(screen.getByText('Live · Checked daily')).toBeInTheDocument();
  });

  it('shows what changed on the page and the page findings', async () => {
    serve({
      item_id: 1042,
      placements: [
        placement({
          latest: snapshot({
            result: 'modified',
            score: 92,
            reopened_item: true,
            diff: [
              { op: 'equal', text: 'fixed rates from ' },
              { op: 'delete', text: '7.49' },
              { op: 'insert', text: '5.99' },
              { op: 'equal', text: '% APR.' },
            ],
            findings: [
              {
                rule_id: 'claims.guaranteed',
                citation: '12 CFR 1026',
                severity: 'blocking',
                message: 'Approval depends on underwriting.',
                suggested_fix: null,
                quote: 'Guaranteed',
                new: true,
              },
            ],
          }),
        }),
      ],
    });
    renderSection();

    expect(await screen.findByText('Changed on the page')).toBeInTheDocument();
    expect(screen.getByText('This check sent the item to re-review.')).toBeInTheDocument();
    const label = screen.getByText('Approved v1 compared with the page');
    const diff = label.parentElement ?? label;
    expect(within(diff).getByText('7.49').closest('del')).not.toBeNull();
    expect(within(diff).getByText('5.99').closest('ins')).not.toBeNull();
    expect(
      screen.getByText(/Code checks on the whole page: 1, 1 not on the approved copy/),
    ).toBeInTheDocument();
    expect(screen.getByText('New on the page')).toBeInTheDocument();
  });

  it('says why a check failed and that nothing changed', async () => {
    serve({
      item_id: 1042,
      placements: [
        placement({
          latest: snapshot({
            status: 'failed',
            result: null,
            error_code: 'timeout',
            error_message: 'The site took too long to respond.',
          }),
        }),
      ],
    });
    renderSection();

    expect(await screen.findByText('Check failed')).toBeInTheDocument();
    expect(
      screen.getByText('The site took too long to respond. Nothing changed on the item.'),
    ).toBeInTheDocument();
  });

  it('flags new blocking findings beside intact approved copy', async () => {
    serve({
      item_id: 1042,
      placements: [
        placement({
          latest: snapshot({
            new_blocking_count: 2,
            findings: [
              {
                rule_id: 'claims.guaranteed',
                citation: '12 CFR 1026',
                severity: 'blocking',
                message: 'Approval depends on underwriting.',
                suggested_fix: null,
                quote: 'Guaranteed approval',
                new: true,
              },
              {
                rule_id: 'claims.credit_impact',
                citation: '12 CFR 1026',
                severity: 'blocking',
                message: 'Credit check claims need support.',
                suggested_fix: null,
                quote: 'no credit check',
                new: true,
              },
            ],
          }),
        }),
      ],
    });
    renderSection();

    expect(await screen.findByText('Unchanged')).toBeInTheDocument();
    const attention = screen.getByText('New blocking findings').closest('.app-badge');
    expect(attention).toHaveAttribute('data-tone', 'alert');
    expect(
      screen.getByText(
        'The approved copy is intact, but text beside it has 2 new blocking findings. The item stays approved.',
      ),
    ).toBeInTheDocument();
  });

  it('shows no attention state for page findings that are on the approved copy too', async () => {
    serve({ item_id: 1042, placements: [placement({ latest: snapshot({ new_blocking_count: 0 }) })] });
    renderSection();

    expect(await screen.findByText('Unchanged')).toBeInTheDocument();
    expect(screen.queryByText('New blocking findings')).not.toBeInTheDocument();
  });

  it('counts a page that keeps returning not found', async () => {
    const gone = {
      status: 'failed' as const,
      result: null,
      http_status: 404,
      error_code: 'http_error',
      error_message: 'The site returned an error. (HTTP 404)',
    };
    serve({ item_id: 1042, placements: [placement({ gone_streak: 2, latest: snapshot(gone) })] });
    renderSection();

    expect(await screen.findByText('Check failed')).toBeInTheDocument();
    expect(
      screen.getByText(
        'The site returned an error. (HTTP 404) Not found on 2 checks in a row. Nothing changed on the item.',
      ),
    ).toBeInTheDocument();
  });

  it('says when a page gone on repeated checks sent the item to re-review', async () => {
    serve({
      item_id: 1042,
      placements: [
        placement({
          gone_streak: 3,
          latest: snapshot({
            status: 'failed',
            result: null,
            http_status: 404,
            error_code: 'http_error',
            error_message: 'The site returned an error. (HTTP 404)',
            reopened_item: true,
          }),
        }),
      ],
    });
    renderSection();

    expect(await screen.findByText('Page not found')).toBeInTheDocument();
    expect(screen.getByText('This check sent the item to re-review.')).toBeInTheDocument();
    expect(
      screen.getByText('The page wasn’t found on 3 checks in a row, so the approved copy counts as missing.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Nothing changed on the item/)).not.toBeInTheDocument();
  });

  it('queues a check, shows it running, and polls until it lands', async () => {
    const queued = snapshot({ status: 'pending', result: null, finished_at: null, trigger: 'manual' });
    const reads = serve(
      { item_id: 1042, placements: [placement({ latest: null })] },
      { item_id: 1042, placements: [placement({ latest: queued })] },
      { item_id: 1042, placements: [placement({ latest: snapshot({ result: 'missing', score: 31 }) })] },
    );
    const posted: string[] = [];
    server.use(
      http.post('*/api/placements/:id/drift-checks', ({ params }) => {
        posted.push(String(params.id));
        return HttpResponse.json(queued, { status: 202 });
      }),
    );
    const user = userEvent.setup();
    renderSection();

    expect(await screen.findByText('Not checked yet.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Check now' }));

    expect(posted).toEqual(['3']);
    expect(await screen.findByText('Checking the page…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Check now' })).toHaveAttribute('data-pending', 'true');
    await waitFor(
      () => {
        expect(screen.getByText('Copy missing')).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
    expect(screen.getByText(/closest match keeps 31% of it/)).toBeInTheDocument();
    expect(reads.gets()).toBeGreaterThanOrEqual(3);
  });

  it('offers the demo edit to leads only, and Check now to the submitter and reviewers', async () => {
    const demo = {
      slug: 'lendcompare',
      partner: 'LendCompare',
      edited: false,
      edit_summary: 'The partner lowers the starting APR.',
      expected: 'modified',
    };
    serve({ item_id: 1042, placements: [placement({ demo_page: demo })] });
    const puts: unknown[] = [];
    server.use(
      http.put('*/api/demo/partner-pages/:slug', async ({ request }) => {
        puts.push(await request.json());
        return HttpResponse.json({ ...demo, url: 'x', edited: true });
      }),
    );
    const user = userEvent.setup();
    const lead = renderSection(['lead', 'reviewer']);

    await user.click(await screen.findByRole('button', { name: 'Simulate partner edit' }));
    expect(puts).toEqual([{ edited: true }]);
    expect(screen.getByText('Demo')).toBeInTheDocument();
    lead.unmount();

    const otherMarketer = renderSection(['marketer'], 55);
    expect(await screen.findByText('Unchanged')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Check now' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Simulate partner edit' })).toBeNull();
    otherMarketer.unmount();

    renderSection(['marketer'], OWNER_ID);
    expect(await screen.findByRole('button', { name: 'Check now' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Simulate partner edit' })).toBeNull();
  });

  it('shows a refused check inline', async () => {
    serve({ item_id: 1042, placements: [placement()] });
    server.use(
      http.post('*/api/placements/:id/drift-checks', () =>
        HttpResponse.json(
          { code: 'not_permitted', message: 'Only the submitter or a reviewer can check a placement.' },
          { status: 403 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByRole('button', { name: 'Check now' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Only the submitter or a reviewer can check a placement.',
    );
  });
});
