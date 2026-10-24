import type { SyntheticEvent } from 'react';

/**
 * Controls inside a row (checkbox, inline editors) stop the click from reaching the row, which would open
 * the preview. React events bubble through portals, so this also covers popovers opened from the cell.
 */
export function stopRowClick(event: SyntheticEvent) {
  event.stopPropagation();
}
