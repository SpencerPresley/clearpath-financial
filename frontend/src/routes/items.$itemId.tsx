import { createFileRoute } from '@tanstack/react-router';

import { ReviewPage } from '../features/review/ReviewPage';
import { reviewSearchSchema } from '../features/review/reviewSearch';

export const Route = createFileRoute('/items/$itemId')({
  validateSearch: reviewSearchSchema,
  component: ReviewRoute,
});

function ReviewRoute() {
  const { itemId } = Route.useParams();
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <ReviewPage
      itemId={Number(itemId)}
      search={search}
      onSearchChange={(next) => {
        void navigate({ search: (prev) => ({ ...prev, ...next }), replace: true });
      }}
    />
  );
}
