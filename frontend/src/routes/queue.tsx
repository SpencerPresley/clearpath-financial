import { createFileRoute, stripSearchParams } from '@tanstack/react-router';

import { QueuePage } from '../features/queue/QueuePage';
import { queueRouteSearchSchema } from '../features/queue/search';
import { RoleGate } from '../ui/layout/RoleGate';

export const Route = createFileRoute('/queue')({
  // Filters, sort, layout, and the preview item are the URL (features/queue/search.ts).
  validateSearch: queueRouteSearchSchema,
  search: { middlewares: [stripSearchParams({ sort: 'queue', layout: 'table' })] },
  component: QueueRoute,
});

function QueueRoute() {
  return (
    <RoleGate page="queue" title="Queue" icon="nav.queue" refusal="The queue is for reviewers and leads">
      <QueuePage />
    </RoleGate>
  );
}
