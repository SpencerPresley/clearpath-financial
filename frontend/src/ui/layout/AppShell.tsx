import { Link, Outlet } from '@tanstack/react-router';
import { useEffect, useRef, useState } from 'react';
import { Button as AriaButton, Focusable } from 'react-aria-components';

import { AssistantPanel } from '../../features/assistant/AssistantPanel';
import { AssistantToggle } from '../../features/assistant/AssistantToggle';
import {
  ASSISTANT_OPEN_EVENT,
  ASSISTANT_PANEL_ID,
  readAssistantOpen,
  writeAssistantOpen,
} from '../../features/assistant/storage';
import { ApiStatusBadge } from '../../features/system/ApiStatusBadge';
import { Icon } from '../Icon';
import { ToastHost } from '../toast';
import { Tooltip } from '../Tooltip';
import { navGroupsFor } from './nav';
import type { NavSection } from './nav';
import { NavLink } from './NavLink';
import { SearchField } from './SearchField';
import { useMediaQuery } from './useMediaQuery';
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

  // The assistant panel: open state persists; opened by the user (not restored on load) means focus moves in.
  const [assistant, setAssistant] = useState(() => ({ open: readAssistantOpen(), byUser: false }));
  const assistantButton = useRef<HTMLButtonElement>(null);
  const [navPinned, setNavPinned] = useState(false);
  const setAssistantOpen = (open: boolean) => {
    writeAssistantOpen(open);
    setAssistant({ open, byUser: true });
    if (!open) setNavPinned(false);
  };
  const closeAssistant = () => {
    // Focus inside the panel is about to unmount with it: hand it to the toggle.
    const inside = document.getElementById(ASSISTANT_PANEL_ID)?.contains(document.activeElement) ?? false;
    setAssistantOpen(false);
    if (inside) assistantButton.current?.focus();
  };
  const toggleAssistant = () => {
    if (assistant.open) closeAssistant();
    else setAssistantOpen(true);
  };
  const toggleAssistantRef = useRef(toggleAssistant);
  useEffect(() => {
    toggleAssistantRef.current = toggleAssistant;
  });
  useEffect(() => {
    // ⌘. / Ctrl+. from anywhere, typing included (useHotkeys skips modified keys by design).
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key === '.') {
        event.preventDefault();
        toggleAssistantRef.current();
      }
    };
    // "Open thread" elsewhere (the Outbox): the panel reads the remembered thread when it mounts.
    const onOpen = () => {
      writeAssistantOpen(true);
      setAssistant((value) => (value.open ? value : { open: true, byUser: true }));
    };
    document.addEventListener('keydown', onKeyDown);
    window.addEventListener(ASSISTANT_OPEN_EVENT, onOpen);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      window.removeEventListener(ASSISTANT_OPEN_EVENT, onOpen);
    };
  }, []);

  // Beside the panel, pages under ~1600px wide lose 400px; the nav steps down to its rail to give some back
  // (review screen decisions, queue columns). The saved choice is untouched and returns when the panel closes;
  // expanding the nav while the panel is open sticks until then.
  const narrowViewport = useMediaQuery('(width < 1600px)');
  const autoCollapsed = assistant.open && narrowViewport && !collapsed && !navPinned;
  const navCollapsed = collapsed || autoCollapsed;
  const navToggleLabel = navCollapsed ? 'Expand navigation' : 'Collapse navigation';
  const toggleNav = () => {
    if (autoCollapsed) setNavPinned(true);
    else toggle();
  };

  return (
    <div className="app-shell">
      <a href="#main" className="app-skip-link">
        Skip to content
      </a>
      <header className="app-topbar">
        <Tooltip content={navToggleLabel} placement="bottom">
          <AriaButton
            className="app-topbar-btn"
            aria-label={navToggleLabel}
            aria-expanded={!navCollapsed}
            aria-controls="primary-nav"
            onPress={toggleNav}
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
          <AssistantToggle buttonRef={assistantButton} open={assistant.open} onPress={toggleAssistant} />
          <UserMenu />
        </div>
      </header>

      <nav
        id="primary-nav"
        aria-label="Primary"
        className="app-nav"
        data-collapsed={navCollapsed ? 'true' : undefined}
      >
        {groups.map((group) => (
          <div key={group.id} className="app-nav-group" role="group" aria-label={group.label}>
            {!navCollapsed && (
              <div className="app-nav-group-label" aria-hidden="true">
                {group.label}
              </div>
            )}
            {group.sections.map((section) => (
              <NavItem key={section.id} section={section} collapsed={navCollapsed} />
            ))}
          </div>
        ))}
      </nav>

      <main id="main" className="app-main" tabIndex={-1}>
        <Outlet />
      </main>
      {assistant.open && <AssistantPanel autoFocus={assistant.byUser} onClose={closeAssistant} />}
      <ToastHost />
    </div>
  );
}
