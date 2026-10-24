import { createFileRoute, Navigate } from '@tanstack/react-router';

import { landingFor } from '../ui/layout/landing';
import { useViewer } from '../ui/layout/Viewer';

// "/" has no screen of its own: it sends each viewer to where their work starts (SessionGate has resolved them).
function Home() {
  const viewer = useViewer();
  return <Navigate to={landingFor(viewer.roles)} replace />;
}

export const Route = createFileRoute('/')({
  component: Home,
});
