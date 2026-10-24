import { createLink } from '@tanstack/react-router';
import type { ReactNode, Ref } from 'react';
import { Link as AriaLink } from 'react-aria-components';
import type { LinkProps as AriaLinkProps } from 'react-aria-components';

import type { ButtonSize, ButtonVariant } from './Button';
import { cx } from './cx';
import { Icon } from './Icon';
import type { IconKey } from './icons';

interface ButtonLinkBaseProps extends Omit<AriaLinkProps, 'className' | 'style' | 'children'> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconKey;
  className?: string;
  children?: ReactNode;
  ref?: Ref<HTMLAnchorElement>;
}

function ButtonLinkBase({
  variant = 'secondary',
  size = 'md',
  icon,
  className,
  children,
  ...props
}: ButtonLinkBaseProps) {
  return (
    <AriaLink {...props} className={cx('app-btn', className)} data-variant={variant} data-size={size}>
      {icon !== undefined && <Icon name={icon} size={size === 'sm' ? 14 : 16} />}
      {children}
    </AriaLink>
  );
}

/**
 * Navigation that looks like a Button (same variants and sizes): "Resubmit", "New submission". A real link
 * (TanStack-typed `to`, opens in a new tab, right-click works) with React Aria's hover and focus states.
 */
export const ButtonLink = createLink(ButtonLinkBase);
