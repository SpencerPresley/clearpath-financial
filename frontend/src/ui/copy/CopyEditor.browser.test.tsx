import '@fontsource-variable/inter/wght.css';
import '../../theme/theme.css';

import { useState } from 'react';
import { expect, it } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-react';

import { CopyEditor } from './CopyEditor';
import type { SpanMark } from './segments';

const LONG = Array.from(
  { length: 14 },
  (_, i) =>
    `Line ${String(i + 1)}: 💸 personal loans as low as 5.99% APR, terms 24–60 months, no impact on your credit score.`,
).join('\n');

function Harness() {
  const [value, setValue] = useState(LONG);
  const start = value.indexOf('no impact');
  const marks: SpanMark[] =
    start === -1
      ? []
      : [{ id: 'f', start, end: start + 9, severity: 'blocking', source: 'code', label: 'f' }];
  return (
    <div style={{ width: 520 }}>
      <CopyEditor label="Copy" value={value} onChange={setValue} marks={marks} />
    </div>
  );
}

// The highlight layer only lines up if the backdrop and the textarea lay text out identically and the
// textarea never scrolls internally; jsdom has no layout, so this runs in Chromium.
it('grows with the copy and keeps the highlight layer the same size as the text', async () => {
  await page.viewport(1280, 800);
  const screen = await render(<Harness />);
  const textarea = screen.getByLabelText('Copy').element() as HTMLTextAreaElement;
  const backdrop = document.querySelector<HTMLElement>('.app-copy-backdrop');
  if (backdrop === null) throw new Error('no highlight backdrop');

  const check = () => {
    expect(textarea.scrollHeight).toBeLessThanOrEqual(textarea.clientHeight + 1);
    expect(
      Math.abs(backdrop.getBoundingClientRect().height - textarea.getBoundingClientRect().height),
    ).toBeLessThan(1);
    const a = getComputedStyle(textarea);
    const b = getComputedStyle(backdrop);
    for (const prop of [
      'font-family',
      'font-size',
      'line-height',
      'padding-left',
      'padding-top',
      'white-space',
      'letter-spacing',
    ] as const) {
      expect(a.getPropertyValue(prop), prop).toBe(b.getPropertyValue(prop));
    }
  };
  check();

  await userEvent.click(textarea);
  await userEvent.keyboard(
    '{Control>}{End}{/Control}\nOne more line that wraps across the editor width to test growth on input.',
  );
  check();
});
