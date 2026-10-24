/*
 * Formatting and period math for the metrics page. Durations under two days read in hours, longer ones in
 * days, always one decimal so figures don't jump width (they also render with tabular figures).
 */
import type { MetricBucket, MetricPointOut } from '../../api/generated/model';
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

export function isoDate(date: Date): string {
  const y = String(date.getFullYear());
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function localDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1);
}

function monday(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() - ((date.getDay() + 6) % 7));
}

/**
 * The period the page asks for. Presets start on a bucket boundary (a Monday, or the 1st), so every bar but the
 * current one is a whole week or month: "13 weeks" is this week to date plus the 12 before it.
 */
export function periodFor(
  search: Pick<MetricsSearch, 'range' | 'from' | 'to'>,
  today: Date = new Date(),
): { from: string; to: string } {
  const to = isoDate(today);
  const thisMonday = monday(today);
  const weeksBack = (weeks: number) =>
    isoDate(new Date(thisMonday.getFullYear(), thisMonday.getMonth(), thisMonday.getDate() - 7 * weeks));
  switch (search.range) {
    case '4w':
      return { from: weeksBack(3), to };
    case '13w':
      return { from: weeksBack(12), to };
    case '12m':
      return { from: isoDate(new Date(today.getFullYear(), today.getMonth() - 11, 1)), to };
    case 'custom':
      return { from: search.from ?? weeksBack(12), to: search.to ?? to };
  }
}

const SHORT = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });
const LONG = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
const MONTH = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric' });

/** "Oct 19" for a week, "Oct 2026" for a month. */
export function bucketLabel(periodStart: string, bucket: MetricBucket): string {
  const date = localDate(periodStart);
  return bucket === 'week' ? SHORT.format(date) : MONTH.format(date);
}

/** "Oct 19 – Oct 24"; with years when the range crosses a year or isn't in the current one. */
export function rangeLabel(from: string, to: string, today: Date = new Date()): string {
  const a = localDate(from);
  const b = localDate(to);
  const years = a.getFullYear() !== b.getFullYear() || b.getFullYear() !== today.getFullYear();
  const f = years ? LONG : SHORT;
  return from === to ? f.format(a) : `${f.format(a)} – ${f.format(b)}`;
}

/** The last day of the bucket starting at `periodStart`. */
function bucketEnd(periodStart: string, bucket: MetricBucket): string {
  const start = localDate(periodStart);
  const end =
    bucket === 'week'
      ? new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6)
      : new Date(start.getFullYear(), start.getMonth() + 1, 0);
  return isoDate(end);
}

/** A bucket the period cuts short (the current week to date, or a custom range's edges). */
export function isPartial(point: MetricPointOut, bucket: MetricBucket): boolean {
  return point.from_date !== point.period_start || point.to_date !== bucketEnd(point.period_start, bucket);
}
