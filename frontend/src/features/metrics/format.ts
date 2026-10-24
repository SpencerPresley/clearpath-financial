/*
 * Formatting and period math for the metrics page. Durations under two days read in hours, longer ones in
 * days, always one decimal so figures don't jump width (they also render with tabular figures).
 */
import type { MetricsSearch } from './search';

export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return '—';
  if (hours === 0) return '0 h';
  if (hours < 48) return `${hours.toFixed(1)} h`;
  return `${(hours / 24).toFixed(1)} d`;
}

export function formatRounds(rounds: number | null | undefined): string {
  return rounds === null || rounds === undefined ? '—' : rounds.toFixed(1);
}

/** "30 native · 12 imported", or which one source the number rests on. */
export function sourceSplit(stat: { native_count: number; imported_count: number }): string {
  const { native_count: native, imported_count: imported } = stat;
  if (native > 0 && imported > 0) return `${String(native)} native · ${String(imported)} imported`;
  if (native > 0) return 'native only';
  if (imported > 0) return 'imported only';
  return '';
}

export const RANGE_DAYS = { '4w': 28, '13w': 91, '12m': 365 } as const;

function isoDate(date: Date): string {
  const y = String(date.getFullYear());
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function daysBefore(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() - days);
}

/** The period the page asks for: a preset ending today (inclusive), or the custom dates. */
export function periodFor(
  search: Pick<MetricsSearch, 'range' | 'from' | 'to'>,
  today: Date = new Date(),
): { from: string; to: string } {
  const to = isoDate(today);
  if (search.range === 'custom') {
    return {
      from: search.from ?? isoDate(daysBefore(today, RANGE_DAYS['13w'] - 1)),
      to: search.to ?? to,
    };
  }
  return { from: isoDate(daysBefore(today, RANGE_DAYS[search.range] - 1)), to };
}

const SHORT = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });
const MONTH = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric' });

function localDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1);
}

/** "Oct 19" for a week, "Oct 2026" for a month. */
export function bucketLabel(periodStart: string, bucket: 'week' | 'month'): string {
  const date = localDate(periodStart);
  return bucket === 'week' ? SHORT.format(date) : MONTH.format(date);
}

/** "Oct 19 – Oct 24". */
export function rangeLabel(from: string, to: string): string {
  return from === to
    ? SHORT.format(localDate(from))
    : `${SHORT.format(localDate(from))} – ${SHORT.format(localDate(to))}`;
}
