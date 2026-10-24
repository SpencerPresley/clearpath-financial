import { describe, expect, it } from 'vitest';

import { FINDINGS_OPEN, dismissedAll, triaged } from '../../test/fixtures/review';
import { decisionGate } from './gate';

const inReview = { status: 'in_review', llm_check_status: 'succeeded', current_version_n: 2 } as const;

describe('decisionGate', () => {
  it('blocks Approve while findings are open and says how many', () => {
    const gate = decisionGate(inReview, FINDINGS_OPEN.slice(0, 2), 2);
    expect(gate.canDecide).toBe(true);
    expect(gate.approve).toEqual({ enabled: false, blockers: ['2 findings to triage'] });
    expect(gate.openCount).toBe(2);
  });

  it('uses the singular for one finding', () => {
    expect(decisionGate(inReview, FINDINGS_OPEN.slice(0, 1), 2).approve.blockers).toEqual([
      '1 finding to triage',
    ]);
  });

  it('enables Approve once everything is dismissed', () => {
    const gate = decisionGate(inReview, dismissedAll(FINDINGS_OPEN), 2);
    expect(gate.approve).toEqual({ enabled: true, blockers: [] });
    expect(gate.approveWithEdits).toEqual({ enabled: true, blockers: [] });
    expect(gate.overrideRequired).toBe(false);
  });

  it('sends accepted findings to Approve with edits: plain Approve would ship copy that must change', () => {
    const gate = decisionGate(inReview, triaged(FINDINGS_OPEN), 2);
    expect(gate.approve).toEqual({ enabled: false, blockers: ['2 accepted findings need a change'] });
    expect(gate.approveWithEdits).toEqual({ enabled: true, blockers: [] });
    expect(gate.acceptedCount).toBe(2);
    expect(decisionGate(inReview, triaged(FINDINGS_OPEN.slice(0, 1)), 2).approve.blockers).toEqual([
      '1 accepted finding needs a change',
    ]);
  });

  it('blocks Approve with edits on the same conditions as Approve, except accepted findings', () => {
    const gate = decisionGate({ ...inReview, llm_check_status: 'running' }, FINDINGS_OPEN.slice(0, 1), 2);
    expect(gate.approveWithEdits.blockers).toEqual(['1 finding to triage', 'AI check running']);
  });

  it('blocks Approve while the AI check is queued or running', () => {
    expect(decisionGate({ ...inReview, llm_check_status: 'pending' }, [], 2).approve.blockers).toEqual([
      'AI check queued',
    ]);
    expect(
      decisionGate({ ...inReview, llm_check_status: 'running' }, dismissedAll(FINDINGS_OPEN), 2).approve,
    ).toEqual({ enabled: false, blockers: ['AI check running'] });
  });

  it('allows Approve after a failed AI check, with an override reason', () => {
    const gate = decisionGate({ ...inReview, llm_check_status: 'failed' }, [], 2);
    expect(gate.approve.enabled).toBe(true);
    expect(gate.overrideRequired).toBe(true);
  });

  it('does not block on a skipped AI check (fast-track versions)', () => {
    const gate = decisionGate({ ...inReview, llm_check_status: 'skipped' }, [], 2);
    expect(gate.approve.enabled).toBe(true);
    expect(gate.overrideRequired).toBe(false);
  });

  it('disables deciding while an older version is shown', () => {
    const gate = decisionGate(inReview, [], 1);
    expect(gate.canDecide).toBe(false);
    expect(gate.approve.blockers).toEqual(['Viewing v1 · decisions apply to v2']);
  });

  it('allows decisions only from submitted or in review', () => {
    for (const status of [
      'approved',
      'rejected',
      'changes_requested',
      'needs_rereview',
      'withdrawn',
    ] as const) {
      expect(decisionGate({ ...inReview, status }, [], 2).canDecide).toBe(false);
    }
    expect(decisionGate({ ...inReview, status: 'submitted' }, [], 2).canDecide).toBe(true);
  });
});
