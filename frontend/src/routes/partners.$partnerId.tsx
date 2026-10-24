import { createFileRoute } from '@tanstack/react-router';

import { PartnerDetailPage } from '../features/partners/PartnerDetailPage';
import { partnerSearchSchema } from '../features/partners/partnersSearch';

export const Route = createFileRoute('/partners/$partnerId')({
  validateSearch: partnerSearchSchema,
  component: PartnerRoute,
});

function PartnerRoute() {
  const { partnerId } = Route.useParams();
  const { tab, rule } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <PartnerDetailPage
      partnerId={Number(partnerId)}
      tab={tab ?? 'items'}
      rule={tab === 'findings' ? rule : undefined}
      onTabChange={(next) => {
        // Switching tabs drops the rule filter: it belongs to the findings history.
        void navigate({ search: { tab: next === 'items' ? undefined : next }, replace: true });
      }}
    />
  );
}
