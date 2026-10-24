import { createFileRoute } from '@tanstack/react-router';

import { PartnerDetailPage } from '../features/partners/PartnerDetailPage';
import { partnerSearchSchema } from '../features/partners/partnersSearch';

export const Route = createFileRoute('/partners/$partnerId')({
  validateSearch: partnerSearchSchema,
  component: PartnerRoute,
});

function PartnerRoute() {
  const { partnerId } = Route.useParams();
  const { tab } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <PartnerDetailPage
      partnerId={Number(partnerId)}
      tab={tab ?? 'items'}
      onTabChange={(next) => {
        void navigate({ search: { tab: next === 'items' ? undefined : next }, replace: true });
      }}
    />
  );
}
