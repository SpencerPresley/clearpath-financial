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
    // Keyed by item: Next item (j) and quick-jump move between items without carrying one item's selection,
    // open form or draft into the next.
    <ReviewPage
      key={itemId}
      itemId={Number(itemId)}
      search={search}
      onSearchChange={(next) => {
        void navigate({ search: (prev) => ({ ...prev, ...next }), replace: true });
      }}
    />
  );
}
