import { createFileRoute } from '@tanstack/react-router';

import { MinePage } from '../features/mine/MinePage';

export const Route = createFileRoute('/mine/')({
  component: MinePage,
});
