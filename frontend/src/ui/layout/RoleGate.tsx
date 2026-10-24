/*
 * A page some roles can't use (landing.ts PAGE_ROLES), opened by URL anyway: say whose page it is and where this
 * person's own work is, at once. The page itself never mounts, so nothing is requested that the server would
 * refuse and nothing sits behind a skeleton (walkthrough-1 S7). Import keeps its own gate in the same words.
 */
import type { ReactNode } from 'react';

import { ButtonLink } from '../ButtonLink';
import { EmptyState } from '../EmptyState';
import type { IconKey } from '../icons';
import { hasAnyRole, LANDING_LABELS, landingFor, PAGE_ROLES } from './landing';
import { useViewer } from './Viewer';

export interface RoleGateProps {
  page: keyof typeof PAGE_ROLES;
  /** The page's own title, kept as the heading so the screen still says where you are. */
  title: string;
  icon: IconKey;
  /** "Metrics is for reviewers, leads and admins". */
  refusal: string;
  children: ReactNode;
}

export function RoleGate({ page, title, icon, refusal, children }: RoleGateProps) {
  const viewer = useViewer();
  if (hasAnyRole(viewer.roles, PAGE_ROLES[page])) return children;
  const landing = landingFor(viewer.roles);
  const label = LANDING_LABELS[landing];
  return (
    <section className="app-gate" aria-labelledby="gate-title">
      <h1 id="gate-title" className="app-page-title">
        {title}
      </h1>
      <div className="app-gate-panel">
        <EmptyState
          icon={icon}
          title={refusal}
          action={
            <ButtonLink to={landing} size="sm">
              Open {label}
            </ButtonLink>
          }
        >
          Your work starts in {label}.
        </EmptyState>
      </div>
    </section>
  );
}
