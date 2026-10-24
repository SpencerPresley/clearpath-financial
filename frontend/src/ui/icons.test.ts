import { describe, expect, it } from 'vitest';

import { FINDING_SOURCES, ITEM_STATUSES, RISK_TIERS, SEVERITIES } from './domain';
import { icons, SHARED_GLYPHS } from './icons';
import type { IconKey } from './icons';

const keys = Object.keys(icons) as IconKey[];

describe('icon registry', () => {
  it('maps different meanings to different glyphs, except the allowlisted shares', () => {
    const allowed = new Map<IconKey, number>();
    SHARED_GLYPHS.forEach((share, index) => {
      share.keys.forEach((key) => allowed.set(key, index));
    });

    const byGlyph = new Map<unknown, IconKey[]>();
    for (const key of keys) {
      const group = byGlyph.get(icons[key].glyph) ?? [];
      group.push(key);
      byGlyph.set(icons[key].glyph, group);
    }

    const collisions = [...byGlyph.values()]
      .filter((group) => group.length > 1)
      .filter((group) => {
        const shares = new Set(group.map((key) => allowed.get(key)));
        return shares.size !== 1 || shares.has(undefined);
      });
    expect(collisions).toEqual([]);
  });

  it('keeps every allowlist entry honest: real keys, really sharing one glyph, with a reason', () => {
    for (const share of SHARED_GLYPHS) {
      expect(share.keys.length).toBeGreaterThanOrEqual(2);
      expect(share.why.length).toBeGreaterThan(10);
      const glyphs = new Set(share.keys.map((key) => icons[key].glyph));
      expect(glyphs.size).toBe(1);
    }
  });

  it('has a glyph for every status, severity, finding source, and risk tier', () => {
    const required = [
      ...ITEM_STATUSES.map((value) => `status.${value}`),
      ...SEVERITIES.map((value) => `severity.${value}`),
      ...RISK_TIERS.map((value) => `risk.${value}`),
      'source.code',
      'source.ai',
      'source.human',
    ];
    expect(FINDING_SOURCES).toHaveLength(3);
    expect(required.filter((key) => !(key in icons))).toEqual([]);
  });

  it('marks finding source by shape: code is filled, AI is outline (spec §5.2)', () => {
    expect(icons['source.code'].weight).toBe('fill');
    expect(icons['source.ai'].weight).toBe('regular');
    expect(icons['source.human'].glyph).not.toBe(icons['source.code'].glyph);
    expect(icons['source.human'].glyph).not.toBe(icons['source.ai'].glyph);
  });
});
