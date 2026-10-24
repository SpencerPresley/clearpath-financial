import { describe, expect, it } from 'vitest';

import {
  DECISION_APPROVED,
  FINDINGS_OPEN,
  itemFixture,
  triaged,
  versionFixture,
} from '../../test/fixtures/review';
import { changesRequestedDraft, fastTrackAvailable } from './decisionModes';

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
