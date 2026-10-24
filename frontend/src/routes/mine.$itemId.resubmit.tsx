import { createFileRoute } from '@tanstack/react-router';

import { ResubmitPage } from '../features/mine/ResubmitPage';
import { RoleGate } from '../ui/layout/RoleGate';

export const Route = createFileRoute('/mine/$itemId/resubmit')({
  component: ResubmitRoute,
});

function ResubmitRoute() {
  const { itemId } = Route.useParams();
  return (
    <RoleGate page="mine" title="Resubmit" icon="nav.my_submissions" refusal="Resubmitting is for marketers">
      <ResubmitPage itemId={Number(itemId)} />
    </RoleGate>
  );
}
