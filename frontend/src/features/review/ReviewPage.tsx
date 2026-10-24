import type { ReviewSearch } from './reviewSearch';

// Placeholder until Task 7 (docs/plan/review-intake.md) lands.
export function ReviewPage({
  itemId,
}: {
  itemId: number;
  search: ReviewSearch;
  onSearchChange: (next: Partial<ReviewSearch>) => void;
}) {
  return <h1 className="app-page-title">CP-{itemId}</h1>;
}
