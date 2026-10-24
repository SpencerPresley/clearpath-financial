/*
 * A file download styled as a small secondary button: a real <a href download> (same-origin session cookie),
 * because the API mutator parses non-JSON bodies as text and would corrupt binary files.
 */
import type { ReactNode } from 'react';
import { Link } from 'react-aria-components';

import { Icon } from './Icon';

export function DownloadLink({
  href,
  filename,
  children,
  'aria-label': ariaLabel,
}: {
  href: string;
  filename?: string | null;
  children: ReactNode;
  'aria-label'?: string;
}) {
  return (
    <Link
      href={href}
      download={filename ?? true}
      aria-label={ariaLabel}
      className="app-btn"
      data-variant="secondary"
      data-size="sm"
    >
      <Icon name="action.download" size={14} />
      {children}
    </Link>
  );
}
