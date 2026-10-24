import { createFileRoute } from '@tanstack/react-router';

import { OutboxPage } from '../features/assistant/outbox/OutboxPage';

export const Route = createFileRoute('/outbox')({
  component: OutboxPage,
});
