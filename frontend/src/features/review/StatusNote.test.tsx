import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DECISION_APPROVED, itemFixture, versionFixture } from '../../test/fixtures/review';
import { renderWithQuery } from '../../test/render';
import { StatusNote } from './StatusNote';

// Walkthrough B1: a terms change generated v2 on a drift re-review. The drift explanation must stay on screen.
const generatedOnDrift = (restored: boolean) =>
  itemFixture({
    status: 'needs_rereview',
    reopen_reason: 'drift_detected',
    live_placements_count: 1,
    latest_decision: { ...DECISION_APPROVED, version_n: 1 },
    current_version: versionFixture(2, { origin: 'fast_track' }),
    numbers_change: true,
    drift_rereview: { placement_id: 3, restored },
  });

function renderNote(item: ReturnType<typeof itemFixture>) {
  renderWithQuery(
    <StatusNote
      item={item}
      viewingCurrent
      shownN={item.current_version_n ?? 0}
      compareN={undefined}
      onShowCurrent={() => undefined}
      onCompareApproved={() => undefined}
    />,
  );
  return screen.getByRole('status');
}

describe('StatusNote', () => {
  it('keeps the drift explanation when terms also changed', () => {
    const note = renderNote(generatedOnDrift(false));
    expect(note).toHaveTextContent(
      'The partner page doesn’t show approved v1. Check it again once the partner restores it, or pull it.',
    );
    expect(note).toHaveTextContent(
      'v2 has the new offer-terms numbers; fast-track it once the page is restored.',
    );
    expect(note).not.toHaveTextContent('was generated with the new numbers.');
  });

  it('explains drift found on a terms re-review too', () => {
    const note = renderNote({ ...generatedOnDrift(false), reopen_reason: 'terms_changed' });
    expect(note).toHaveTextContent('The partner page doesn’t show approved v1.');
  });

  it('goes back to the fast-track message once the copy is restored', () => {
    const note = renderNote(generatedOnDrift(true));
    expect(note).toHaveTextContent('v2 was generated with the new numbers.');
  });
});
