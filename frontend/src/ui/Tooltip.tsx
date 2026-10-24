import type { ReactElement, ReactNode } from 'react';
import { Tooltip as AriaTooltip, TooltipTrigger } from 'react-aria-components';
import type { Placement } from 'react-aria-components';

export interface TooltipProps {
  content: ReactNode;
  /** Must be focusable: a RAC Button, Link, or an element wrapped in RAC <Focusable>. */
  children: ReactElement;
  placement?: Placement;
  /** Hover delay in ms. Keyboard focus shows immediately. */
  delay?: number;
}

export function Tooltip({ content, children, placement = 'top', delay = 500 }: TooltipProps) {
  return (
    <TooltipTrigger delay={delay} closeDelay={100}>
      {children}
      <AriaTooltip className="app-tooltip" placement={placement} offset={6}>
        {content}
      </AriaTooltip>
    </TooltipTrigger>
  );
}
