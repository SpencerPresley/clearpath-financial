import { Button as AriaButton } from 'react-aria-components';
import type { Ref } from 'react';
import type { ButtonProps as AriaButtonProps } from 'react-aria-components';

import { cx } from './cx';
import { Icon } from './Icon';
import type { IconKey } from './icons';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends Omit<AriaButtonProps, 'className' | 'style'> {
  /** primary: the one main action in a view. danger: destructive only (reject, pull, reset). */
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Leading icon from the registry; decorative, the label names the button. */
  icon?: IconKey;
  className?: string;
  /** React 19 passes ref as a prop; it reaches the DOM button (e.g. to return focus to it). */
  ref?: Ref<HTMLButtonElement>;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <AriaButton {...props} className={cx('app-btn', className)} data-variant={variant} data-size={size}>
      {(renderProps) => (
        <>
          {icon !== undefined && <Icon name={icon} size={size === 'sm' ? 14 : 16} />}
          {typeof children === 'function' ? children(renderProps) : children}
        </>
      )}
    </AriaButton>
  );
}
