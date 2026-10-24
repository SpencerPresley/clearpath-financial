import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RiskTierBadge, SeverityBadge, SourceTag, STATUS_META, StatusBadge, StatusMark } from './badges';
import { ITEM_STATUSES } from './domain';
import type { ItemStatus } from './domain';

// Spec §5.2 color meaning table, restated here so a change to STATUS_META has to change the test too.
const EXPECTED: Record<ItemStatus, [label: string, tone: string]> = {
  draft: ['Draft', 'neutral'],
  submitted: ['Submitted', 'neutral'],
  in_review: ['In review', 'info'],
  changes_requested: ['Changes requested', 'warning'],
  approved: ['Approved', 'success'],
  rejected: ['Rejected', 'error'],
  needs_rereview: ['Needs re-review', 'alert'],
  expired: ['Expired', 'neutral'],
  withdrawn: ['Withdrawn', 'neutral'],
};

describe('StatusBadge', () => {
  it.each(ITEM_STATUSES)('%s renders its label, icon, and §5.2 tone', (status) => {
    const [label, tone] = EXPECTED[status];
    render(<StatusBadge status={status} />);
    const badge = screen.getByText(label).closest('[data-tone]');
    expect(badge).toHaveAttribute('data-tone', tone);
    expect(badge?.querySelector(`svg[data-icon="status.${status}"]`)).not.toBeNull();
    expect(STATUS_META[status].label).toBe(label);
  });

  it('gives every status a distinct glyph, so neutral statuses differ by more than text', () => {
    const glyphs = new Set(ITEM_STATUSES.map((status) => STATUS_META[status].icon));
    expect(glyphs.size).toBe(ITEM_STATUSES.length);
  });
});

describe('SeverityBadge', () => {
  it('maps blocking to error and warning to warning, with filled glyphs', () => {
    const { container } = render(
      <>
        <SeverityBadge severity="blocking" />
        <SeverityBadge severity="warning" />
      </>,
    );
    expect(screen.getByText('Blocking').closest('[data-tone]')).toHaveAttribute('data-tone', 'error');
    expect(screen.getByText('Warning').closest('[data-tone]')).toHaveAttribute('data-tone', 'warning');
    container.querySelectorAll('svg').forEach((svg) => {
      expect(svg).toHaveAttribute('data-weight', 'fill');
    });
  });
});

describe('SourceTag', () => {
  it.each([
    ['code', 'Code check', 'source.code', 'fill'],
    ['llm', 'AI suggestion', 'source.ai', 'regular'],
    ['human', 'Checklist', 'source.human', 'regular'],
  ] as const)('%s reads "%s" with %s (%s)', (source, label, icon, weight) => {
    render(<SourceTag source={source} />);
    const tag = screen.getByText(label).closest('.app-source');
    const svg = tag?.querySelector('svg');
    expect(svg).toHaveAttribute('data-icon', icon);
    expect(svg).toHaveAttribute('data-weight', weight);
    // Source is shape and label, not color (spec §5.2).
    expect(tag).not.toHaveAttribute('data-tone');
  });
});

describe('RiskTierBadge', () => {
  it.each([
    ['high', 'High risk'],
    ['medium', 'Medium risk'],
    ['low', 'Low risk'],
  ] as const)('%s reads "%s" and borrows no status color', (tier, label) => {
    render(<RiskTierBadge tier={tier} />);
    const badge = screen.getByText(label).closest('[data-tone]');
    expect(badge).toHaveAttribute('data-tone', 'neutral');
    expect(badge?.querySelector(`svg[data-icon="risk.${tier}"]`)).not.toBeNull();
  });
});

describe('StatusMark (dense cells, spec §5.2a)', () => {
  it.each(ITEM_STATUSES)('%s is an icon named by its label, with the §5.2 tone and no tab stop', (status) => {
    const [label, tone] = EXPECTED[status];
    render(<StatusMark status={status} />);
    const mark = screen.getByRole('img', { name: label });
    expect(mark).toHaveAttribute('data-tone', tone);
    expect(mark).toHaveAttribute('title', label);
    expect(mark).not.toHaveAttribute('tabindex');
    expect(mark.querySelector(`svg[data-icon="status.${status}"]`)).not.toBeNull();
  });
});
