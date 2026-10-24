import { createFileRoute } from '@tanstack/react-router';

import { MinePage } from '../features/mine/MinePage';
import { RoleGate } from '../ui/layout/RoleGate';

export const Route = createFileRoute('/mine/')({
  component: MineRoute,
});

function MineRoute() {
  return (
    <RoleGate
      page="mine"
      title="My submissions"
      icon="nav.my_submissions"
      refusal="My submissions is for marketers"
    >
      <MinePage />
    </RoleGate>
  );
}
