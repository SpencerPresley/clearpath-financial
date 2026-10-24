import { Linter } from 'eslint';
import { describe, expect, it } from 'vitest';

import { noRawPaletteRule } from './noRawPalette';

function lint(code: string): string[] {
  const linter = new Linter({ configType: 'flat' });
  return linter
    .verify(code, [
      {
        plugins: { clearpath: { rules: { 'no-raw-palette': noRawPaletteRule } } },
        rules: { 'clearpath/no-raw-palette': 'error' },
        languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
      },
    ])
    .map((message) => message.message);
}

describe('clearpath/no-raw-palette', () => {
  it.each([
    ['<div className="bg-blue-500" />', 'bg-blue-500'],
    ['<div className="p-2 hover:text-red-600/50" />', 'text-red-600'],
    ['cx(`border-l-slate-200 ${x}`)', 'border-l-slate-200'],
    ['const c = "ring-offset-emerald-50";', 'ring-offset-emerald-50'],
    ['<div className="bg-[#fff]" />', 'bg-[#'],
    ['<div className="text-[oklch(50%_0.1_250)]" />', 'text-[oklch('],
    ['<div className="rounded-2xl" />', 'rounded-2xl'],
    ['<div className="shadow-lg" />', 'shadow-lg'],
  ])('reports %s', (code, offender) => {
    const messages = lint(code);
    expect(messages).toHaveLength(1);
    expect(messages[0]).toContain(offender);
  });

  it.each([
    '<div className="bg-neutral text-neutral-content" />',
    '<div className="bg-base-100 text-base-content border-base-300" />',
    '<div className="bg-status-alert-soft text-status-alert-soft-content" />',
    '<div className="rounded-lg shadow-overlay text-ui" />',
    'const label = "Changes requested";',
    'const to = "to-do list";',
  ])('allows %s', (code) => {
    expect(lint(code)).toEqual([]);
  });
});
