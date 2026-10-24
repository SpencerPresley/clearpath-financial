import { createFileRoute } from '@tanstack/react-router';

import { SubmitPage } from '../features/submit/SubmitPage';
import { RoleGate } from '../ui/layout/RoleGate';

export const Route = createFileRoute('/submit')({
  component: SubmitRoute,
});

function SubmitRoute() {
  return (
    <RoleGate
      page="submit"
      title="New submission"
      icon="nav.new_submission"
      refusal="New submission is for marketers"
    >
      <SubmitPage />
    </RoleGate>
  );
}
