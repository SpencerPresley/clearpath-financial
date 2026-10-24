import { useEffect, useState } from 'react';
import { Button as AriaButton } from 'react-aria-components';

import { Icon } from './Icon';
import { Tooltip } from './Tooltip';

type CopyState = 'idle' | 'copied' | 'failed';

const FEEDBACK_MS = 1500;

export interface ItemKeyProps {
  /** The display key, e.g. "CP-1042". */
  value: string;
  /** Show a copy control (on hover/focus). Default true. */
  copyable?: boolean;
}

export function ItemKey({ value, copyable = true }: ItemKeyProps) {
  const [state, setState] = useState<CopyState>('idle');

  useEffect(() => {
    if (state === 'idle') return;
    const timer = window.setTimeout(() => {
      setState('idle');
    }, FEEDBACK_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [state]);

  const copy = () => {
    // The Clipboard API rejects outside secure contexts or without permission; say so, don't throw.
    navigator.clipboard.writeText(value).then(
      () => {
        setState('copied');
      },
      () => {
        setState('failed');
      },
    );
  };

  const feedback = state === 'copied' ? 'Copied' : state === 'failed' ? "Couldn't copy" : '';

  return (
    <span className="app-item-key">
      <span className="font-mono">{value}</span>
      {copyable && (
        <>
          <Tooltip content={feedback || `Copy ${value}`}>
            <AriaButton
              className="app-item-key-copy"
              aria-label={`Copy ${value}`}
              onPress={copy}
              data-copied={state === 'idle' ? undefined : true}
            >
              <Icon name="action.copy" size={14} />
            </AriaButton>
          </Tooltip>
          <span role="status" className="sr-only">
            {feedback}
          </span>
        </>
      )}
    </span>
  );
}
