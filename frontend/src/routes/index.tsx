import { createFileRoute } from '@tanstack/react-router';

import { QueuePage } from '../features/queue/QueuePage';

export const Route = createFileRoute('/')({
  component: QueuePage,
});
