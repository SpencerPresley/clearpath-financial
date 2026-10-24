import { createFileRoute } from '@tanstack/react-router';

import { ImportPage } from '../features/import/ImportPage';
import { importSearchSchema } from '../features/import/search';

export const Route = createFileRoute('/import')({
  // The job and the chosen step are the URL (features/import/search.ts).
  validateSearch: importSearchSchema,
  component: ImportPage,
});
