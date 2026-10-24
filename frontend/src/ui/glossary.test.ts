import { describe, expect, it } from 'vitest';

import { DriftResult, LlmFailureCode, ReopenReason, RiskTier, TermsField } from '../api/generated/model';
import {
  DRIFT_CONCEPT_LABEL,
  DRIFT_RESULT_LABELS,
  LLM_FAILURE_LABELS,
  REOPEN_REASON_LABELS,
  RISK_TIER_LABELS,
  TERMS_FIELD_LABELS,
} from './labels';

describe('glossary (spec §5.4: one term per concept)', () => {
  it('names drift one way: "Live copy changed", with Unchanged / Changed / Missing results', () => {
    expect(REOPEN_REASON_LABELS.drift_detected).toBe('Live copy changed');
    expect(DRIFT_CONCEPT_LABEL).toBe(REOPEN_REASON_LABELS.drift_detected);
    expect(DRIFT_RESULT_LABELS).toEqual({ unchanged: 'Unchanged', modified: 'Changed', missing: 'Missing' });
  });

  it('uses "Offer terms changed" for the terms reopen reason', () => {
    expect(REOPEN_REASON_LABELS.terms_changed).toBe('Offer terms changed');
  });

  it('labels every generated enum member', () => {
    for (const r of Object.values(ReopenReason)) expect(REOPEN_REASON_LABELS[r]).toMatch(/\S/);
    for (const d of Object.values(DriftResult)) expect(DRIFT_RESULT_LABELS[d]).toMatch(/\S/);
    for (const t of Object.values(RiskTier)) expect(RISK_TIER_LABELS[t]).toMatch(/\S/);
    for (const f of Object.values(TermsField)) expect(TERMS_FIELD_LABELS[f]).not.toMatch(/_/);
    for (const c of Object.values(LlmFailureCode)) expect(LLM_FAILURE_LABELS[c]).toMatch(/\.$/);
  });

  it('uses the Offer terms screen’s field names', () => {
    expect(TERMS_FIELD_LABELS.apr_min).toBe('APR min');
    expect(TERMS_FIELD_LABELS.term_months).toBe('Loan terms (months)');
    expect(TERMS_FIELD_LABELS.origination_fee_min_pct).toBe('Origination fee min');
  });

  it('describes provider failures without HTTP status codes', () => {
    expect(LLM_FAILURE_LABELS.provider_unavailable).not.toMatch(/\d{3}|provider/i);
  });
});
