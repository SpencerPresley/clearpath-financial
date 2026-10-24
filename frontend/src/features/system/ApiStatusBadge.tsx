import { Focusable } from 'react-aria-components';

import { useHealth } from '../../api/generated';
import { Icon } from '../../ui/Icon';
import { Tooltip } from '../../ui/Tooltip';

const RECHECK_MS = 30_000;

/**
 * API health in the topbar. Quiet when healthy (a muted glyph, named for screen readers), prominent
 * when down, invisible while the first check is in flight so it doesn't flash on every load.
 * The indicators are role="img" so they can carry a tooltip (RAC Focusable needs an interactive or img
 * role); the down state sits in a role="alert" wrapper so the change is announced.
 */
export function ApiStatusBadge() {
  const { data, isPending, isError } = useHealth({
    query: { retry: false, refetchInterval: RECHECK_MS },
  });

  if (isPending) {
    return (
      <span role="status" className="sr-only">
        Checking API
      </span>
    );
  }
  if (isError || data.status !== 'ok') {
    return (
      <span role="alert">
        <Tooltip content="Changes can't be saved right now. Rechecking every 30 seconds." placement="bottom">
          <Focusable>
            <span role="img" aria-label="API unavailable" className="app-api-down">
              <Icon name="system.api_offline" size={14} />
              <span>API unavailable</span>
            </span>
          </Focusable>
        </Tooltip>
      </span>
    );
  }
  return (
    <Tooltip content="API online" placement="bottom">
      <Focusable>
        <span role="img" aria-label="API online" className="app-api-quiet">
          <Icon name="system.api_online" size={16} />
        </span>
      </Focusable>
    </Tooltip>
  );
}
