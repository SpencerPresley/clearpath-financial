/*
 * WCAG 2.2 contrast for the oklch() tokens in theme.css. Used by contrast.test.ts (the AA gate) and the
 * design gallery (live ratios). Conversion: OKLCH -> OKLab -> LMS -> linear sRGB (Björn Ottosson's
 * matrices), then WCAG relative luminance on the linear channels.
 */

const OKLCH = /^oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)\s*\)$/;

/** Linear-light sRGB channels for an `oklch(L% C H)` string. Out-of-gamut values fall outside [0, 1]. */
export function oklchToSrgb(value: string): [number, number, number] {
  const match = OKLCH.exec(value.trim());
  if (match === null) {
    throw new Error(`Not an oklch() color: ${value}`);
  }
  const [, lRaw = '0', percent, cRaw = '0', hRaw = '0'] = match;
  const L = percent === '%' ? Number(lRaw) / 100 : Number(lRaw);
  const C = Number(cRaw);
  const h = (Number(hRaw) * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);

  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;

  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

function luminance(value: string): number {
  const [r, g, b] = oklchToSrgb(value).map((channel) => Math.min(1, Math.max(0, channel))) as [
    number,
    number,
    number,
  ];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(foreground: string, background: string): number {
  const a = luminance(foreground);
  const b = luminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** Every `--name: value;` declaration in a stylesheet, keyed without the leading dashes. Last one wins. */
export function readTokens(css: string): Record<string, string> {
  const tokens: Record<string, string> = {};
  for (const match of css.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    const [, name, value] = match;
    if (name !== undefined && value !== undefined) tokens[name] = value.trim();
  }
  return tokens;
}

/** Follows `var(--x)` references until a literal value. */
export function resolveToken(tokens: Record<string, string>, name: string): string {
  const seen = new Set<string>();
  let current = name;
  for (;;) {
    const value = tokens[current];
    if (value === undefined) throw new Error(`Unknown token --${current}`);
    const ref = /^var\(--([\w-]+)\)$/.exec(value);
    if (ref?.[1] === undefined) return value;
    if (seen.has(ref[1])) throw new Error(`Cycle at --${ref[1]}`);
    seen.add(current);
    current = ref[1];
  }
}
