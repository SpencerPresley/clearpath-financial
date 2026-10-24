import { Button as AriaButton } from 'react-aria-components';
import type { ButtonProps as AriaButtonProps } from 'react-aria-components';

import type { ButtonSize, ButtonVariant } from './Button';
import { cx } from './cx';
import { Icon } from './Icon';
import type { IconKey } from './icons';
import { Tooltip } from './Tooltip';

export interface IconButtonProps extends Omit<AriaButtonProps, 'className' | 'style' | 'children'> {
  icon: IconKey;
  /** Required: an icon-only button has no other name (spec §5.2a). Also used as the tooltip text. */
  'aria-label': string;
  /** Show aria-label as a tooltip on hover/focus. Default true. */
  tooltip?: boolean;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
}

export function IconButton({
  icon,
  tooltip = true,
  variant = 'ghost',
  size = 'md',
  className,
  ...props
}: IconButtonProps) {
  const button = (
    <AriaButton
      {...props}
      className={cx('app-btn app-btn-icon', className)}
      data-variant={variant}
      data-size={size}
    >
      <Icon name={icon} size={size === 'sm' ? 14 : 16} />
    </AriaButton>
  );
  return tooltip ? <Tooltip content={props['aria-label']}>{button}</Tooltip> : button;
}
