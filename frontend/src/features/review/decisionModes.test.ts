import { describe, expect, it } from 'vitest';

import {
  DECISION_APPROVED,
  FINDINGS_OPEN,
  itemFixture,
  triaged,
  versionFixture,
} from '../../test/fixtures/review';
import { changesRequestedDraft, fastTrackAvailable, rereviewActions } from './decisionModes';

describe('rereviewActions', () => {
  const approvedV1 = { ...DECISION_APPROVED, version_n: 1 };
  const rereview = (
    reopen_reason: 'terms_changed' | 'approval_expired' | 'drift_detected',
    generated = false,
  ) =>
    itemFixture({
      status: 'needs_rereview',
      reopen_reason,
      latest_decision: generated ? approvedV1 : DECISION_APPROVED,
      ...(generated ? { current_version: versionFixture(2, { origin: 'fast_track' }) } : {}),
    });

  it('never offers reaffirm after a terms change', () => {
    expect(rereviewActions(rereview('terms_changed', true))).toEqual(['fast_track', 'pull']);
    expect(rereviewActions(rereview('terms_changed'))).toEqual(['review', 'pull']);
  });

  it('offers reaffirm for an expired approval or live-copy drift', () => {
    expect(rereviewActions(rereview('approval_expired'))).toEqual(['reaffirm', 'pull']);
    expect(rereviewActions(rereview('drift_detected'))).toEqual(['reaffirm', 'pull']);
  });

  it('offers nothing outside re-review', () => {
    expect(rereviewActions(itemFixture())).toEqual([]);
  });
});

describe('fastTrackAvailable', () => {
  const generated = versionFixture(2, { origin: 'fast_track' });

  it('is available for a generated version newer than the approval', () => {
    const item = itemFixture({
      status: 'needs_rereview',
      reopen_reason: 'terms_changed',
      current_version: generated,
      latest_decision: { ...DECISION_APPROVED, version_n: 1 },
    });
    expect(fastTrackAvailable(item)).toBe(true);
  });

  it('is not available for an expiring approval with no generated version', () => {
    const item = itemFixture({
      status: 'needs_rereview',
      reopen_reason: 'approval_expired',
      latest_decision: DECISION_APPROVED,
    });
    expect(fastTrackAvailable(item)).toBe(false);
  });

  it('is not available outside re-review', () => {
    expect(
      fastTrackAvailable(
        itemFixture({ current_version: generated, latest_decision: { ...DECISION_APPROVED, version_n: 1 } }),
      ),
    ).toBe(false);
  });
});

describe('changesRequestedDraft', () => {
  it('lists accepted findings with their quotes', () => {
    expect(changesRequestedDraft(triaged(FINDINGS_OPEN))).toBe(
      [
        '- Rate claim needs the full APR range (“as low as 5.99% APR”)',
        '- “As low as” may need a creditworthiness qualifier (“as low as”)',
      ].join('\n'),
    );
  });

  it('is empty when nothing was accepted', () => {
    expect(changesRequestedDraft(FINDINGS_OPEN)).toBe('');
  });
});
