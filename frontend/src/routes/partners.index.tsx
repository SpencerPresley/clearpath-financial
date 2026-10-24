import { createFileRoute } from '@tanstack/react-router';

import { PartnersPage } from '../features/partners/PartnersPage';
import { partnersSearchSchema } from '../features/partners/partnersSearch';

export const Route = createFileRoute('/partners/')({
  validateSearch: partnersSearchSchema,
  component: PartnersRoute,
});

function PartnersRoute() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <PartnersPage
      search={search}
      onSearchChange={(next, options) => {
        void navigate({ search: (prev) => ({ ...prev, ...next }), replace: options?.replace });
      }}
    />
  );
}
