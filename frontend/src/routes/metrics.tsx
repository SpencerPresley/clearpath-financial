import { createFileRoute, stripSearchParams } from '@tanstack/react-router';

import { MetricsPage } from '../features/metrics/MetricsPage';
import { metricsSearchSchema, SEARCH_DEFAULTS } from '../features/metrics/search';

export const Route = createFileRoute('/metrics')({
  // Period, filters, trend, and the open drill-down are the URL (features/metrics/search.ts).
  validateSearch: metricsSearchSchema,
  search: { middlewares: [stripSearchParams(SEARCH_DEFAULTS)] },
  component: MetricsPage,
});
