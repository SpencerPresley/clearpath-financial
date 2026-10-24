import { render } from 'vitest-browser-react';
import { expect, it } from 'vitest';

import { QueuePage } from './QueuePage';

it('renders the queue heading in a real browser', async () => {
  const screen = await render(<QueuePage />);

  await expect.element(screen.getByRole('heading', { name: 'Review queue' })).toBeVisible();
});
