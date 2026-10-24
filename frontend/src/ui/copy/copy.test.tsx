import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { CheckPreviewIn, CheckPreviewOut } from '../../api/generated/model';
import { server } from '../../test/server';
import { CopyEditor } from './CopyEditor';
import { DiffText, countChanges } from './DiffText';
import { HighlightedText } from './HighlightedText';
import type { SpanMark } from './segments';
import { useLiveChecks } from './useLiveChecks';

const TEXT = 'Rates as low as 5.99% APR.';
const MARKS: SpanMark[] = [
  {
    id: 'f1',
    start: 6,
    end: 15,
    severity: 'blocking',
    source: 'code',
    quote: 'as low as',
    label: 'Blocking',
  },
  { id: 'f2', start: 6, end: 21, severity: 'warning', source: 'llm', label: 'Warning' },
];

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function input(text: string): CheckPreviewIn {
  return { content_text: text, product: 'personal_loan', channel: 'paid_social', markets: ['national'] };
}

describe('HighlightedText', () => {
  it('renders the text once with marks', () => {
    const { container } = render(<HighlightedText text={TEXT} marks={MARKS} />);
    expect(container.textContent).toBe(TEXT);
    const marks = container.querySelectorAll('mark');
    expect([...marks].map((m) => m.textContent)).toEqual(['as low as', ' 5.99%']);
    expect(marks[0]).toHaveAttribute('data-severity', 'blocking');
    expect(marks[1]).toHaveAttribute('data-source', 'llm');
  });

  it('cycles through overlapping marks on repeated clicks', async () => {
    const onMarkPress = vi.fn();
    const { container, rerender } = render(
      <HighlightedText text={TEXT} marks={MARKS} onMarkPress={onMarkPress} />,
    );
    const first = container.querySelector('mark');
    if (first === null) throw new Error('no mark');
    await userEvent.click(first);
    expect(onMarkPress).toHaveBeenLastCalledWith('f1');
    rerender(<HighlightedText text={TEXT} marks={MARKS} activeId="f1" onMarkPress={onMarkPress} />);
    await userEvent.click(first);
    expect(onMarkPress).toHaveBeenLastCalledWith('f2');
  });
});

describe('CopyEditor', () => {
  it('draws marks under the typed text and reports edits', async () => {
    const onChange = vi.fn();
    const { container } = render(<CopyEditor label="Copy" value={TEXT} onChange={onChange} marks={MARKS} />);
    expect(container.querySelector('.app-copy-backdrop mark')?.textContent).toBe('as low as');
    await userEvent.type(screen.getByLabelText('Copy'), '!');
    expect(onChange).toHaveBeenLastCalledWith(`${TEXT}!`);
  });
});

describe('DiffText', () => {
  it('labels insertions and deletions for screen readers', () => {
    render(
      <DiffText
        segments={[
          { op: 'equal', text: 'as low as ' },
          { op: 'delete', text: '5.99' },
          { op: 'insert', text: '6.49' },
        ]}
      />,
    );
    expect(screen.getByText('5.99').closest('del')).not.toBeNull();
    expect(screen.getByText('6.49').closest('ins')).not.toBeNull();
    expect(screen.getByText('removed:')).toBeInTheDocument();
  });

  it('counts contiguous changes once', () => {
    expect(
      countChanges([
        { op: 'equal', text: 'a' },
        { op: 'delete', text: 'b' },
        { op: 'insert', text: 'c' },
        { op: 'equal', text: 'd' },
        { op: 'insert', text: 'e' },
      ]),
    ).toBe(2);
  });
});

describe('useLiveChecks', () => {
  it('sends one request for a burst of edits and marks the latest text', async () => {
    const bodies: CheckPreviewIn[] = [];
    server.use(
      http.post('*/api/checks/preview', async ({ request }) => {
        const body = (await request.json()) as CheckPreviewIn;
        bodies.push(body);
        const start = body.content_text.indexOf('as low as');
        const out: CheckPreviewOut = {
          ruleset_key: 'k',
          terms_refs: [],
          findings: [
            {
              rule_id: 'pricing.as_low_as_range',
              citation: 'Reg Z 12 CFR 1026.24(a)',
              source: 'code',
              severity: 'blocking',
              message: 'Rate claim needs the full APR range',
              suggested_fix: '',
              span: { start, end: start + 9 },
              quote: 'as low as',
            },
          ],
        };
        return HttpResponse.json(out);
      }),
    );

    const { result, rerender } = renderHook(({ value }) => useLiveChecks(input(value)), {
      wrapper,
      initialProps: { value: '' },
    });
    rerender({ value: 'Rates' });
    rerender({ value: 'Rates as' });
    rerender({ value: TEXT });

    await waitFor(() => {
      expect(result.current.status).toBe('ready');
    });
    expect(bodies.map((b) => b.content_text)).toEqual([TEXT]);
    expect(result.current.marks.map((m) => TEXT.slice(m.start, m.end))).toEqual(['as low as']);

    // An edit before the span: the stale mark hides until the next response.
    rerender({ value: `New: ${TEXT}` });
    expect(result.current.status).toBe('checking');
    expect(result.current.marks).toEqual([]);
  });

  it('stays idle without copy', () => {
    const { result } = renderHook(() => useLiveChecks(input('   ')), { wrapper });
    expect(result.current.status).toBe('idle');
  });
});
