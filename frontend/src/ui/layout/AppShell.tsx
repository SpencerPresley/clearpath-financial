import { Link, Outlet } from '@tanstack/react-router';
import { useState } from 'react';
import { Button as AriaButton, Focusable } from 'react-aria-components';

import { ApiStatusBadge } from '../../features/system/ApiStatusBadge';
import { Icon } from '../Icon';
import { ToastHost } from '../toast';
import { Tooltip } from '../Tooltip';
import { navGroupsFor } from './nav';
import type { NavSection } from './nav';
import { NavLink } from './NavLink';
import { SearchField } from './SearchField';
import { UserMenu } from './UserMenu';
import { useViewer } from './Viewer';

export const NAV_COLLAPSED_KEY = 'clearpath.nav.collapsed';

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(NAV_COLLAPSED_KEY) === 'true';
  } catch {
    return false; // storage blocked (privacy mode): fall back to expanded
  }
}

function writeCollapsed(value: boolean) {
  try {
    window.localStorage.setItem(NAV_COLLAPSED_KEY, String(value));
  } catch {
    // storage blocked: the choice lasts for this page view only
  }
}

function NavItem({ section, collapsed }: { section: NavSection; collapsed: boolean }) {
  const label = <span className={collapsed ? 'sr-only' : 'app-nav-item-label'}>{section.label}</span>;

  if (section.to === undefined) {
    // Not built yet: a disabled link (no href, no placeholder page). Focusable so keyboard users can
    // discover it, with the same tooltip as real links when the rail is collapsed.
    const item = (
      <span
        role="link"
        aria-disabled="true"
        aria-label={`${section.label}, soon`}
        tabIndex={0}
        className="app-nav-item"
      >
        <Icon name={section.icon} />
        {label}
        {!collapsed && <span className="app-nav-item-note">Soon</span>}
      </span>
    );
    return collapsed ? (
      <Tooltip content={`${section.label} · Soon`} placement="right">
        <Focusable>{item}</Focusable>
      </Tooltip>
    ) : (
      item
    );
  }

  const link = (
    <NavLink to={section.to} className="app-nav-item">
      <Icon name={section.icon} />
      {label}
    </NavLink>
  );
  return collapsed ? (
    <Tooltip content={section.label} placement="right">
      {link}
    </Tooltip>
  ) : (
    link
  );
}

export function AppShell() {
  const viewer = useViewer();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const groups = navGroupsFor(viewer.roles);

  const toggle = () => {
    setCollapsed((value) => {
      writeCollapsed(!value);
      return !value;
    });
  };
  const toggleLabel = collapsed ? 'Expand navigation' : 'Collapse navigation';

  return (
    <div className="app-shell">
      <a href="#main" className="app-skip-link">
        Skip to content
      </a>
      <header className="app-topbar">
        <Tooltip content={toggleLabel} placement="bottom">
          <AriaButton
            className="app-topbar-btn"
            aria-label={toggleLabel}
            aria-expanded={!collapsed}
            aria-controls="primary-nav"
            onPress={toggle}
          >
            <Icon name="action.toggle_nav" size={18} />
          </AriaButton>
        </Tooltip>
        <Link to="/" className="app-wordmark" aria-label="ClearPath Compliance Review">
          <span className="app-wordmark-mark" aria-hidden="true" />
          <span aria-hidden="true">ClearPath</span>
          <span className="app-wordmark-product" aria-hidden="true">
            Compliance Review
          </span>
        </Link>
        <SearchField />
        <div className="app-topbar-end">
          <ApiStatusBadge />
          <UserMenu />
        </div>
      </header>

      <nav
        id="primary-nav"
        aria-label="Primary"
        className="app-nav"
        data-collapsed={collapsed ? 'true' : undefined}
      >
        {groups.map((group) => (
          <div key={group.id} className="app-nav-group" role="group" aria-label={group.label}>
            {!collapsed && (
              <div className="app-nav-group-label" aria-hidden="true">
                {group.label}
              </div>
            )}
            {group.sections.map((section) => (
              <NavItem key={section.id} section={section} collapsed={collapsed} />
            ))}
          </div>
        ))}
      </nav>

      <main id="main" className="app-main" tabIndex={-1}>
        <Outlet />
      </main>
      <ToastHost />
    </div>
  );
}
