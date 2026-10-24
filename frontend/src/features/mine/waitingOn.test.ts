import { describe, expect, it } from 'vitest';

import { DECISION_APPROVED, DECISION_CHANGES, REVIEWER, itemRowFixture } from '../../test/fixtures/review';
import { waitingOn } from './waitingOn';

describe('waitingOn', () => {
  it('changes requested: on you, with who asked and the first line of why (from the row alone)', () => {
    const row = itemRowFixture({ status: 'changes_requested', latest_decision: DECISION_CHANGES });
    expect(waitingOn(row)).toEqual({
      bucket: 'you',
      why: 'Dana Reyes: Add the California license line.',
      action: 'resubmit',
    });
  });

  it('changes requested with no decision on record: still on you, no invented reason', () => {
    expect(waitingOn(itemRowFixture({ status: 'changes_requested' }))).toEqual({
      bucket: 'you',
      why: 'Changes requested',
      action: 'resubmit',
    });
  });

  it('withdrawn and expired: on you, start a new round', () => {
    expect(waitingOn(itemRowFixture({ status: 'withdrawn' }))).toEqual({
      bucket: 'you',
      why: 'Pulled. Start a new round when the copy is fixed.',
      action: 'new_round',
    });
    expect(waitingOn(itemRowFixture({ status: 'expired' }))).toEqual({
      bucket: 'you',
      why: 'Approval expired. Start a new round to run it again.',
      action: 'new_round',
    });
  });

  it('draft: on you, nothing to do from here', () => {
    expect(waitingOn(itemRowFixture({ status: 'draft' }))).toEqual({
      bucket: 'you',
      why: 'Not submitted yet',
    });
  });

  it('submitted: with compliance, named when assigned', () => {
    expect(waitingOn(itemRowFixture({ status: 'submitted', assignee: null }))).toEqual({
      bucket: 'compliance',
      why: 'Waiting for a reviewer',
    });
    expect(waitingOn(itemRowFixture({ status: 'submitted', assignee: REVIEWER }))).toEqual({
      bucket: 'compliance',
      why: 'With Dana Reyes',
    });
  });

  it('in review: with compliance, who is reviewing', () => {
    expect(waitingOn(itemRowFixture({ status: 'in_review', assignee: REVIEWER }))).toEqual({
      bucket: 'compliance',
      why: 'Dana Reyes is reviewing',
    });
    expect(waitingOn(itemRowFixture({ status: 'in_review', assignee: null })).why).toBe('In review');
  });

  it('needs re-review: with compliance, with the reopen reason', () => {
    expect(waitingOn(itemRowFixture({ status: 'needs_rereview', reopen_reason: 'terms_changed' }))).toEqual({
      bucket: 'compliance',
      why: 'Back in review: Offer terms changed',
    });
    expect(waitingOn(itemRowFixture({ status: 'needs_rereview', reopen_reason: null })).why).toBe(
      'Back in review',
    );
  });

  it('approved: with the expiry date from the row', () => {
    expect(waitingOn(itemRowFixture({ status: 'approved', approval_expires_at: null }))).toEqual({
      bucket: 'approved',
      why: 'Approved',
    });
    const row = itemRowFixture({ status: 'approved', approval_expires_at: '2027-04-24T00:00:00Z' });
    expect(waitingOn(row).why).toMatch(/^Approved · expires Apr 2[34], 2027$/);
  });

  it('rejected: closed', () => {
    expect(waitingOn(itemRowFixture({ status: 'rejected' }))).toEqual({
      bucket: 'closed',
      why: 'Rejected',
    });
  });

  it('ignores a latest decision that is not a change request', () => {
    const row = itemRowFixture({ status: 'changes_requested', latest_decision: DECISION_APPROVED });
    expect(waitingOn(row).why).toBe('Changes requested');
  });
});
