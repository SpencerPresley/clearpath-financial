import { createFileRoute } from '@tanstack/react-router';

import { SubmitPage } from '../features/submit/SubmitPage';

export const Route = createFileRoute('/submit')({
  component: SubmitPage,
});
