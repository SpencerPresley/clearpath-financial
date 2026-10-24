import { createFileRoute } from '@tanstack/react-router';

import { ResubmitPage } from '../features/mine/ResubmitPage';

export const Route = createFileRoute('/mine/$itemId/resubmit')({
  component: ResubmitRoute,
});

function ResubmitRoute() {
  const { itemId } = Route.useParams();
  return <ResubmitPage itemId={Number(itemId)} />;
}
