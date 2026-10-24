import { createLink } from '@tanstack/react-router';
import { Link as AriaLink } from 'react-aria-components';

/**
 * TanStack-typed `to` + React Aria Link states (data-hovered, data-focus-visible) and tooltip support.
 * Pattern from TanStack Router's custom-link guide (React Aria Components >= 1.11).
 */
export const NavLink = createLink(AriaLink);
