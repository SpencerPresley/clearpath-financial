import { describe, expect, it } from 'vitest';

import type { ItemHistoryOut } from '../../api/generated/model';
import { HISTORY, REVIEWER } from '../../test/fixtures/review';
import { describeEvent } from './historyText';

type Entry = ItemHistoryOut['entries'][number];

const versions = new Map([
  [501, 1],
  [502, 2],
]);
const users = new Map([[21, REVIEWER.name]]);

function base<T extends Entry['type']>(type: T) {
  return {
    id: 99,
    type,
    actor: REVIEWER,
    at: '2026-10-24T10:00:00Z',
    entity: 'item' as const,
    entity_id: 1042,
    from_status: null,
    to_status: null,
  };
}

describe('describeEvent', () => {
  it('describes the fixture timeline', () => {
    expect(HISTORY.entries.map((e) => describeEvent(e, { versions, users }))).toEqual([
      'Submitted v1',
      'Assigned to Dana Reyes · Lowest load',
      'Changes requested on v1: Add the California license line.',
      'Resubmitted v2 (round 2)',
    ]);
  });

  it('names dismissals, carried dismissals, and reopenings', () => {
    const dismissed: Entry = {
      ...base('finding.dismissed'),
      payload: {
        finding_id: 1,
        rule_id: 'claims.credit_impact',
        reason: 'Limited to rate check',
        carried: false,
        version_id: 502,
      },
    };
    const carried: Entry = { ...dismissed, payload: { ...dismissed.payload, carried: true } };
    expect(describeEvent(dismissed, { versions, users })).toBe(
      'Dismissed claims.credit_impact on v2: Limited to rate check',
    );
    expect(describeEvent(carried, { versions, users })).toBe(
      'Dismissal of claims.credit_impact carried to v2: Limited to rate check',
    );
  });

  it('describes AI check outcomes and re-review', () => {
    const failed: Entry = {
      ...base('llm_check.failed'),
      payload: { check_run_id: 1, version_id: 502, error: 'timeout' },
    };
    const succeeded: Entry = {
      ...base('llm_check.succeeded'),
      payload: { check_run_id: 1, version_id: 502, findings_count: 2, dropped_findings_count: 1 },
    };
    const reopened: Entry = {
      ...base('item.reopened'),
      payload: { reason: 'terms_changed', offer_terms_id: 13, generated_version_id: 503 },
    };
    expect(describeEvent(failed, { versions, users })).toBe('AI check failed on v2');
    expect(describeEvent(succeeded, { versions, users })).toBe('AI check finished on v2 · 2 suggestions');
    expect(describeEvent(reopened, { versions, users })).toBe('Sent to re-review: Offer terms changed');
  });

  it('describes drift attention and repeated failed checks', () => {
    const flagged: Entry = {
      ...base('placement.page_findings_flagged'),
      actor: null,
      payload: { placement_id: 3, snapshot_id: 9, rule_ids: ['claims.guaranteed', 'claims.credit_impact'] },
    };
    const gone: Entry = {
      ...base('item.reopened'),
      actor: null,
      payload: { reason: 'drift_detected', snapshot_id: 9, failed_snapshot_ids: [9, 8, 7] },
    };
    expect(describeEvent(flagged, { versions, users })).toBe(
      'Placement checked: copy unchanged, 2 new blocking findings beside it',
    );
    expect(describeEvent(gone, { versions, users })).toBe(
      'Sent to re-review: Live copy changed (page couldn’t be fetched on 3 checks in a row)',
    );
  });

  it('falls back to the event type', () => {
    const odd: Entry = { ...base('demo.reset'), payload: { seeded_items: 3 } };
    expect(describeEvent(odd, { versions, users })).toBe('demo.reset');
  });
});
