import { createFileRoute, stripSearchParams } from '@tanstack/react-router';

import { LibraryPage } from '../features/library/LibraryPage';
import { LIBRARY_DEFAULTS, librarySearchSchema } from '../features/library/search';

export const Route = createFileRoute('/library')({
  // The view, the precedent query and mode, and the filters are the URL (features/library/search.ts).
  validateSearch: librarySearchSchema,
  search: { middlewares: [stripSearchParams(LIBRARY_DEFAULTS)] },
  component: LibraryPage,
});
