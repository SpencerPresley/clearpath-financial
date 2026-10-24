import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Focusable } from 'react-aria-components';

import { getHealthQueryKey, useHealth } from '../../api/generated';
import { ApiError } from '../../api/mutator';
import { Icon } from '../../ui/Icon';
import { Tooltip } from '../../ui/Tooltip';

const RECHECK_MS = 30_000;

/** A failure that says the server may be gone: never reached it, or a proxy/server error. A 4xx came from it. */
function mayBeDown(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status >= 500;
}

/**
 * API health in the topbar. Healthy is the absence of a signal: nothing visible and no tab stop, only
 * screen-reader text. Down is prominent and says the consequence ("changes won't save"), inside a
 * role="alert" wrapper so the change is announced. The first check renders nothing visible, so the
 * topbar doesn't flash on every load. A save that fails for want of a server rechecks at once, so the banner
 * arrives with the failing toast instead of up to 30 s later.
 */
export function ApiStatusBadge() {
  const queryClient = useQueryClient();
  const { data, isPending, isError } = useHealth({
    query: { retry: false, refetchInterval: RECHECK_MS },
  });

  useEffect(
    () =>
      queryClient.getMutationCache().subscribe((event) => {
        if (event.type !== 'updated' || event.action.type !== 'error') return;
        if (mayBeDown(event.action.error)) {
          void queryClient.invalidateQueries({ queryKey: getHealthQueryKey() });
        }
      }),
    [queryClient],
  );

  if (isPending) {
    return <span className="sr-only">Checking server connection</span>;
  }
  if (isError || data.status !== 'ok') {
    return (
      <span role="alert">
        <Tooltip content="Rechecking every 30 seconds." placement="bottom">
          <Focusable>
            {/* role="img": RAC Focusable needs an interactive or img role on a tooltip trigger. */}
            <span
              role="img"
              aria-label="Can't reach the server. Changes won't save."
              className="app-api-down"
            >
              <Icon name="system.api_offline" size={14} />
              <span>Can't reach server · changes won't save</span>
            </span>
          </Focusable>
        </Tooltip>
      </span>
    );
  }
  return <span className="sr-only">Server connected</span>;
}
