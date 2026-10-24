import { Focusable } from 'react-aria-components';

import { Tooltip } from './Tooltip';

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * Compact age for dense views: "now", "12m", "5h", "3d", "2w", "4mo", "1y".
 * Days until two weeks (queue SLAs are counted in days), then weeks, months (30d), years (365d).
 * A future timestamp (client clock behind the server) clamps to "now".
 */
export function formatAge(at: Date, now: Date): string {
  const seconds = Math.max(0, Math.floor((now.getTime() - at.getTime()) / 1000));
  if (seconds < MINUTE) return 'now';
  if (seconds < HOUR) return `${String(Math.floor(seconds / MINUTE))}m`;
  if (seconds < DAY) return `${String(Math.floor(seconds / HOUR))}h`;
  const days = Math.floor(seconds / DAY);
  if (days < 14) return `${String(days)}d`;
  if (days < 60) return `${String(Math.floor(days / 7))}w`;
  if (days < 365) return `${String(Math.floor(days / 30))}mo`;
  return `${String(Math.floor(days / 365))}y`;
}

const absoluteFormat = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
});

export interface RelativeAgeProps {
  at: string | Date;
  /** Reference time; defaults to render time. Pass it in tests and for lists that share one clock. */
  now?: Date;
}

export function RelativeAge({ at, now }: RelativeAgeProps) {
  const date = at instanceof Date ? at : new Date(at);
  if (Number.isNaN(date.getTime())) {
    return <span className="app-age">—</span>;
  }
  const age = formatAge(date, now ?? new Date());
  const absolute = absoluteFormat.format(date);
  // role="img" + aria-label: the spoken name is the absolute time ("3d" reads badly), and RAC's
  // Focusable requires an interactive or img role on a tooltip trigger.
  return (
    <Tooltip content={absolute}>
      <Focusable>
        <time className="app-age" dateTime={date.toISOString()} role="img" aria-label={absolute}>
          {age}
        </time>
      </Focusable>
    </Tooltip>
  );
}
