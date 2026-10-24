import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SnippetText } from './SnippetText';

describe('SnippetText', () => {
  it('marks only the highlighted parts and keeps the rest as plain text', () => {
    const { container } = render(
      <SnippetText
        parts={[
          { text: '…checking your rate ', highlighted: false },
          { text: "won't affect your credit score", highlighted: true },
          { text: '. Loans from $2,000', highlighted: false },
        ]}
      />,
    );

    const marks = container.querySelectorAll('mark');
    expect([...marks].map((m) => m.textContent)).toEqual(["won't affect your credit score"]);
    expect(container.textContent).toBe(
      "…checking your rate won't affect your credit score. Loans from $2,000",
    );
  });

  it('renders markup in the copy as text, never as HTML', () => {
    const { container } = render(
      <SnippetText parts={[{ text: '<img src=x onerror=alert(1)> as low as', highlighted: true }]} />,
    );

    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('<img src=x onerror=alert(1)> as low as').tagName).toBe('MARK');
  });
});
