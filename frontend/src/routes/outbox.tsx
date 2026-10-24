import { createFileRoute } from '@tanstack/react-router';

import { OutboxPage, outboxSearchSchema } from '../features/assistant/outbox/OutboxPage';

export const Route = createFileRoute('/outbox')({
  validateSearch: outboxSearchSchema,
  component: OutboxRoute,
});

function OutboxRoute() {
  const { email } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <OutboxPage
      selectedId={email}
      onSelect={(id) => {
        void navigate({ search: { email: id }, replace: true });
      }}
    />
  );
}
