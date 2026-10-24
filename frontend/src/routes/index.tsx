import { createFileRoute, stripSearchParams } from '@tanstack/react-router';

import { QueuePage } from '../features/queue/QueuePage';
import { queueRouteSearchSchema } from '../features/queue/search';

export const Route = createFileRoute('/')({
  // Filters, sort, layout, and the preview item are the URL (features/queue/search.ts).
  validateSearch: queueRouteSearchSchema,
  search: { middlewares: [stripSearchParams({ sort: 'queue', layout: 'table' })] },
  component: QueuePage,
});
