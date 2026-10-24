import { describe, expect, it } from 'vitest';

import { NAV_SECTIONS, navGroupsFor, navSectionsFor } from './nav';

const labels = (roles: Parameters<typeof navSectionsFor>[0]) =>
  navSectionsFor(roles).map((section) => section.label);

describe('navSectionsFor', () => {
  it('shows a marketer their submissions and shared sections only', () => {
    expect(labels(['marketer'])).toEqual(['My submissions', 'New submission', 'Library', 'Outbox']);
  });

  it('shows a reviewer the queue and the read-only offer terms and partners, not metrics or import', () => {
    expect(labels(['reviewer'])).toEqual(['Queue', 'Library', 'Offer terms', 'Partners', 'Outbox']);
  });

  it('shows a lead the queue plus offer terms, partners, and metrics', () => {
    expect(labels(['lead'])).toEqual(['Queue', 'Library', 'Offer terms', 'Partners', 'Metrics', 'Outbox']);
  });

  it('shows an admin import and shared sections', () => {
    expect(labels(['admin'])).toEqual(['Library', 'Import', 'Outbox']);
  });

  it('unions roles in a stable order, without duplicates', () => {
    expect(labels(['admin', 'reviewer'])).toEqual([
      'Queue',
      'Library',
      'Offer terms',
      'Partners',
      'Import',
      'Outbox',
    ]);
    expect(labels(['reviewer', 'lead', 'reviewer'])).toEqual(labels(['lead']));
  });

  it('shows everything for all four roles (the demo viewer)', () => {
    expect(labels(['marketer', 'reviewer', 'lead', 'admin'])).toEqual(
      NAV_SECTIONS.map((section) => section.label),
    );
  });

  it('shows only shared sections for a user with no roles', () => {
    expect(labels([])).toEqual(['Library', 'Outbox']);
  });
});

describe('navGroupsFor', () => {
  it('drops groups that end up empty for the viewer', () => {
    expect(navGroupsFor(['admin']).map((group) => group.label)).toEqual(['Reference', 'Operations']);
  });

  it('keeps the registry icon for every section', () => {
    for (const section of NAV_SECTIONS) {
      expect(section.icon.startsWith('nav.')).toBe(true);
    }
  });
});
