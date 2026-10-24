import { describe, expect, it } from 'vitest';

import { contrastRatio, oklchToSrgb, readTokens, resolveToken } from './contrast';
import themeCss from './theme.css?raw';

const tokens = readTokens(themeCss);

const TONES = ['neutral', 'info', 'warning', 'success', 'error', 'alert'] as const;

// [foreground, background, minimum]. 4.5 = WCAG 2.2 AA body text (1.4.3); 3 = non-text (1.4.11).
const PAIRS: [string, string, number][] = [
  ['base-content', 'base-100', 4.5],
  ['base-content', 'base-200', 4.5],
  ['muted', 'base-100', 4.5],
  ['muted', 'base-200', 4.5],
  ['primary-content', 'primary', 4.5],
  ['brand-accent', 'primary', 4.5],
  ['brand-muted', 'primary', 4.5],
  ['primary', 'base-100', 4.5],
  ['primary', 'nav-active', 4.5],
  ['secondary-content', 'secondary', 4.5],
  ['neutral-content', 'neutral', 4.5],
  ['focus', 'base-100', 3],
  ['focus', 'base-200', 3],
  ['focus-on-brand', 'primary', 3],
  ...TONES.flatMap((tone): [string, string, number][] => [
    [`status-${tone}-content`, `status-${tone}`, 4.5],
    [`status-${tone}-soft-content`, `status-${tone}-soft`, 4.5],
    [`status-${tone}-soft-content`, 'base-100', 4.5],
  ]),
  // daisyUI aliases resolve to the same values; checked so a drift in either place fails here.
  ['info-content', 'info', 4.5],
  ['success-content', 'success', 4.5],
  ['warning-content', 'warning', 4.5],
  ['error-content', 'error', 4.5],
];

describe('contrastRatio', () => {
  it('is 21 for black on white and 1 for a color on itself', () => {
    expect(contrastRatio('oklch(0% 0 0)', 'oklch(100% 0 0)')).toBeCloseTo(21, 1);
    expect(contrastRatio('oklch(50% 0.1 250)', 'oklch(50% 0.1 250)')).toBeCloseTo(1, 5);
  });

  it('matches a known sRGB pair (#767676 on white is 4.54)', () => {
    // #767676: linear 0.1812, OKLab L = cbrt(0.1812) = 0.5658
    expect(contrastRatio('oklch(56.58% 0 0)', 'oklch(100% 0 0)')).toBeCloseTo(4.54, 1);
  });
});

describe('theme tokens', () => {
  it('keeps every color token inside the sRGB gamut, so the ratio below is what renders', () => {
    const outOfGamut = Object.keys(tokens)
      .filter((name) => name.startsWith('color-'))
      .filter((name) => {
        const value = resolveToken(tokens, name);
        if (!value.startsWith('oklch(')) return false;
        return oklchToSrgb(value).some((channel) => channel < -0.001 || channel > 1.001);
      });
    expect(
      outOfGamut.map(
        (n) =>
          `${n} ${resolveToken(tokens, n)} ${oklchToSrgb(resolveToken(tokens, n))
            .map((c) => c.toFixed(4))
            .join(',')}`,
      ),
    ).toEqual([]);
  });

  it.each(PAIRS)('%s on %s meets %d:1', (fg, bg, min) => {
    const ratio = contrastRatio(resolveToken(tokens, `color-${fg}`), resolveToken(tokens, `color-${bg}`));
    expect(ratio).toBeGreaterThanOrEqual(min);
  });

  it('prints the ratio table for the report', () => {
    const rows = PAIRS.map(([fg, bg, min]) => {
      const ratio = contrastRatio(resolveToken(tokens, `color-${fg}`), resolveToken(tokens, `color-${bg}`));
      return `| ${fg} | ${bg} | ${ratio.toFixed(2)} | ${String(min)} |`;
    });
    // PRINT_CONTRAST=1 npx vitest run --project unit src/theme/contrast.test.ts
    const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env;
    if (env?.PRINT_CONTRAST) console.log(['| fg | bg | ratio | min |', ...rows].join('\n'));
    expect(rows).toHaveLength(PAIRS.length);
  });
});
