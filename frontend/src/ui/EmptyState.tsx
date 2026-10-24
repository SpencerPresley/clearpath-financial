import type { ReactNode } from 'react';

import { Icon } from './Icon';
import type { IconKey } from './icons';

export interface EmptyStateProps {
  /** The entity or section that's empty, from the registry. */
  icon: IconKey;
  /** Why it's empty, in domain terms: "Nothing assigned to you", not "No data". */
  title: string;
  /** One line of context, e.g. "4 unassigned items". */
  children?: ReactNode;
  /** The next action, usually one Button. */
  action?: ReactNode;
}

/** Inline in the data region, left-aligned with the content it replaces; not a centered hero (§5.6). */
export function EmptyState({ icon, title, children, action }: EmptyStateProps) {
  return (
    <div className="app-empty">
      <Icon name={icon} size={20} className="app-empty-icon" />
      <div>
        <h2 className="app-empty-title">{title}</h2>
        {children !== undefined && <p className="app-empty-detail">{children}</p>}
        {action !== undefined && <div className="app-empty-action">{action}</div>}
      </div>
    </div>
  );
}
