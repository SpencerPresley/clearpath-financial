import { describe, expect, it } from 'vitest';

import { GetItemHistoryResponse } from '../../api/generated/items/items.zod';

import type { ItemHistoryOut } from '../../api/generated/model';
import { HISTORY, REVIEWER } from '../../test/fixtures/review';
import { EVENT_SENTENCES, describeEvent } from './historyText';

type Entry = ItemHistoryOut['entries'][number];

const versions = new Map([
  [501, 1],
  [502, 2],
]);
const users = new Map([[21, REVIEWER.name]]);
const findings = new Map([[1, 'Credit-impact claims need evidence of the pull type.']]);

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
    expect(describeEvent(dismissed, { versions, users, findings })).toBe(
      'Dismissed “Credit-impact claims need evidence of the pull type” on v2: Limited to rate check',
    );
    expect(describeEvent(carried, { versions, users, findings })).toBe(
      'Dismissal of “Credit-impact claims need evidence of the pull type” carried to v2: Limited to rate check',
    );
    // Before the finding's version has loaded: still no rule id on screen.
    expect(describeEvent(dismissed, { versions, users })).toBe(
      'Dismissed a finding on v2: Limited to rate check',
    );
  });

  it('never shows a rule id, enum value or event type', () => {
    const accepted: Entry = {
      ...base('finding.accepted'),
      payload: { finding_id: 1, rule_id: 'claims.credit_impact', version_id: 501 },
    };
    const started: Entry = {
      ...base('llm_check.started'),
      payload: { check_run_id: 1, version_id: 502, attempt: 1 },
    };
    const risk: Entry = { ...base('item.risk_tier_overridden'), payload: { before: 'low', after: 'high' } };
    const checked: Entry = {
      ...base('placement.drift_checked'),
      payload: {
        placement_id: 3,
        snapshot_id: 9,
        status: 'succeeded',
        result: 'modified',
        compared_version_id: 501,
      },
    };
    const failedCheck: Entry = {
      ...base('placement.drift_checked'),
      payload: { placement_id: 3, snapshot_id: 9, status: 'failed', error_code: 'address_not_allowed' },
    };
    const lines = [accepted, started, risk, checked, failedCheck].map((e) =>
      describeEvent(e, { versions, users, findings }),
    );
    expect(lines).toEqual([
      'Accepted “Credit-impact claims need evidence of the pull type” on v1',
      'AI check started on v2',
      'Risk tier changed from Low to High',
      'Placement checked against v1: Changed',
      'Placement check failed: the page couldn’t be fetched',
    ]);
    for (const line of lines) expect(line).not.toMatch(/[a-z]+[._][a-z]+/);
  });

  it('has a sentence for every event type the API can return', () => {
    const union = GetItemHistoryResponse.shape.entries.element;
    const types = union.options.map((option) => option.shape.type.value);
    expect(types.length).toBeGreaterThan(40);
    expect(types.filter((type) => !(type in EVENT_SENTENCES))).toEqual([]);
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
      'Placement checked: Unchanged, 2 new blocking findings beside it',
    );
    expect(describeEvent(gone, { versions, users })).toBe(
      'Sent to re-review: Live copy changed (page couldn’t be fetched on 3 daily checks in a row)',
    );
  });

  it('describes system events in words too', () => {
    const odd: Entry = { ...base('demo.reset'), payload: { seeded_items: 3 } };
    expect(describeEvent(odd, { versions, users })).toBe('Demo reset');
  });
});
