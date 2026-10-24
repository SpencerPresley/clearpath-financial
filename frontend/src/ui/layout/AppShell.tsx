import { Link, Outlet } from '@tanstack/react-router';

import { ApiStatusBadge } from '../../features/system/ApiStatusBadge';

const PLACEHOLDER_SECTIONS = ['Submit', 'Library', 'Offer terms', 'Partners'] as const;

export function AppShell() {
  return (
    <div className="app-shell">
      <header className="app-topbar">
        <span className="app-brand">ClearPath · Compliance Review</span>
        <ApiStatusBadge />
      </header>
      <nav aria-label="Primary" className="app-sidebar">
        <ul className="menu w-full">
          <li>
            <Link to="/" activeProps={{ className: 'menu-active' }}>
              Queue
            </Link>
          </li>
          {PLACEHOLDER_SECTIONS.map((section) => (
            <li key={section} className="menu-disabled">
              <span aria-disabled="true">{section}</span>
            </li>
          ))}
        </ul>
      </nav>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
