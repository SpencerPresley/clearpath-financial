import { createFileRoute } from '@tanstack/react-router';

import { TermsPage } from '../features/terms/TermsPage';
import { termsSearchSchema } from '../features/terms/termsSearch';

export const Route = createFileRoute('/terms')({
  validateSearch: termsSearchSchema,
  component: TermsRoute,
});

function TermsRoute() {
  const { product } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <TermsPage
      product={product ?? 'personal_loan'}
      onProductChange={(next) => {
        void navigate({ search: { product: next === 'personal_loan' ? undefined : next } });
      }}
    />
  );
}
