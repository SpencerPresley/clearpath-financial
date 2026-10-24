import { describe, expect, it } from 'vitest';

import { Channel, DecisionOutcome, Product, ReopenReason } from '../../api/generated/model';
import { CHANNEL_LABEL, OUTCOME_LABEL, PRODUCT_LABEL, REOPEN_REASON_LABEL, roundLabel } from './labels';

describe('labels', () => {
  it('labels every generated enum member', () => {
    for (const p of Object.values(Product)) expect(PRODUCT_LABEL[p]).toMatch(/\S/);
    for (const c of Object.values(Channel)) expect(CHANNEL_LABEL[c]).toMatch(/\S/);
    for (const r of Object.values(ReopenReason)) expect(REOPEN_REASON_LABEL[r]).toMatch(/\S/);
    for (const o of Object.values(DecisionOutcome)) expect(OUTCOME_LABEL[o]).toMatch(/\S/);
  });

  it('uses glossary wording', () => {
    expect(REOPEN_REASON_LABEL.terms_changed).toBe('Terms changed');
    expect(OUTCOME_LABEL.approved_with_edits).toBe('Approved with edits');
    expect(OUTCOME_LABEL.changes_requested).toBe('Changes requested');
    expect(PRODUCT_LABEL.mortgage_prequal).toBe('Mortgage prequal');
    expect(CHANNEL_LABEL.sms).toBe('SMS');
  });

  it('formats rounds', () => {
    expect(roundLabel(1)).toBe('R1');
    expect(roundLabel(3)).toBe('R3');
  });
});
