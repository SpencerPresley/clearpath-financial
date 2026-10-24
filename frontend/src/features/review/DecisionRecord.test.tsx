import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { DecisionOut } from '../../api/generated/model';
import { DECISION_APPROVED, DECISION_CHANGES } from '../../test/fixtures/review';
import { DecisionRecord, aiReviewLine } from './DecisionRecord';

function row(label: string): HTMLElement {
  const term = screen.getByText(label, { selector: 'dt' });
  const value = term.nextElementSibling;
  if (!(value instanceof HTMLElement)) throw new Error(`no value for ${label}`);
  return value;
}

describe('DecisionRecord', () => {
  it('renders every fact the approval recorded', () => {
    render(<DecisionRecord decision={{ ...DECISION_APPROVED, engine_version: '2026-10-24.3' }} />);

    expect(row('Outcome')).toHaveTextContent('Approved v2');
    expect(row('Decided by')).toHaveTextContent('Dana Reyes');
    expect(row('Decided by')).toHaveTextContent('Oct 24, 2026');
    expect(row('Reason')).toHaveTextContent('Range and license line present');
    expect(row('Offer terms')).toHaveTextContent('Personal loan v12');
    expect(row('Rule set')).toHaveTextContent('Jul 21, 2026');
    expect(row('Engine')).toHaveTextContent('2026-10-24.3');
    expect(row('AI review')).toHaveTextContent('Ran on v2');
    expect(row('Expires')).toHaveTextContent('Apr 2');
    const evidence = within(row('Evidence'));
    expect(evidence.getByText(/rate-sheet-oct\.pdf/)).toBeInTheDocument();
    // A short hash, with the full one on hover.
    const hash = evidence.getByText('sha256 4f9c2a1be07d…');
    expect(hash).toHaveAttribute('title', DECISION_APPROVED.evidence[0]?.sha256);
  });

  it('names the lane, the AI override reason, and what was carried', () => {
    const fastTrack: DecisionOut = {
      ...DECISION_APPROVED,
      version_n: 4,
      lane: 'fast_track',
      ai_review_carried_from_n: 3,
      terms_versions: [
        { id: 12, product: 'personal_loan', version: 3 },
        { id: 20, product: 'credit_card', version: 2 },
      ],
      evidence: [],
    };
    render(<DecisionRecord decision={fastTrack} />);
    expect(row('Outcome')).toHaveTextContent('Approved v4 · Fast-track');
    expect(row('AI review')).toHaveTextContent('Carried from v3');
    expect(row('Offer terms')).toHaveTextContent('Personal loan v3');
    expect(row('Offer terms')).toHaveTextContent('Credit card v2');
    expect(row('Evidence')).toHaveTextContent('None relied on');
  });

  it('words the AI status from the record', () => {
    expect(aiReviewLine({ ...DECISION_APPROVED, llm_override_reason: 'Provider outage; read by hand' })).toBe(
      'Overridden after the AI check failed',
    );
    expect(aiReviewLine({ ...DECISION_APPROVED, ai_review_carried_from_n: 1 })).toBe('Carried from v1');
    expect(aiReviewLine(DECISION_APPROVED)).toBe('Ran on v2');
    // Request changes / reject don't pass the AI gate, so the record says nothing about it.
    expect(aiReviewLine(DECISION_CHANGES)).toBeNull();
  });

  it('leaves out approval-only facts on a change request', () => {
    render(<DecisionRecord decision={DECISION_CHANGES} />);
    expect(row('Outcome')).toHaveTextContent('Changes requested on v1');
    expect(screen.queryByText('AI review', { selector: 'dt' })).not.toBeInTheDocument();
    expect(screen.queryByText('Expires', { selector: 'dt' })).not.toBeInTheDocument();
    expect(screen.queryByText('Offer terms', { selector: 'dt' })).not.toBeInTheDocument();
  });
});
