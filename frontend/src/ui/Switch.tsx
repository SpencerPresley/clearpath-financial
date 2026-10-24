/*
 * An on/off switch (React Aria SwitchField + SwitchButton: a real role="switch" input, keyboard and focus
 * handled). For settings that apply at once, like availability; a form choice is a checkbox. The label is visible
 * text, or `aria-label` when a row already says whose it is.
 */
import type { ReactNode } from 'react';
import { SwitchButton, SwitchField } from 'react-aria-components';

import { cx } from './cx';

export interface SwitchProps {
  isSelected: boolean;
  onChange: (isSelected: boolean) => void;
  isDisabled?: boolean;
  children?: ReactNode;
  'aria-label'?: string;
  className?: string;
}

export function Switch({ children, className, ...props }: SwitchProps) {
  return (
    <SwitchField {...props} className="app-switch-field">
      <SwitchButton className={cx('app-switch', className)}>
        <span className="app-switch-track" aria-hidden="true">
          <span className="app-switch-thumb" />
        </span>
        {children}
      </SwitchButton>
    </SwitchField>
  );
}
