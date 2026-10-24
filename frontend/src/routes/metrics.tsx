import { createFileRoute, stripSearchParams } from '@tanstack/react-router';

import { MetricsPage } from '../features/metrics/MetricsPage';
import { metricsSearchSchema, SEARCH_DEFAULTS } from '../features/metrics/search';
import { RoleGate } from '../ui/layout/RoleGate';

export const Route = createFileRoute('/metrics')({
  // Period, filters, trend, and the open drill-down are the URL (features/metrics/search.ts).
  validateSearch: metricsSearchSchema,
  search: { middlewares: [stripSearchParams(SEARCH_DEFAULTS)] },
  component: MetricsRoute,
});

function MetricsRoute() {
  return (
    <RoleGate
      page="metrics"
      title="Metrics"
      icon="nav.metrics"
      refusal="Metrics is for reviewers, leads and admins"
    >
      <MetricsPage />
    </RoleGate>
  );
}
