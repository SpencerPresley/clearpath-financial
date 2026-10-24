/*
 * The metrics page's URL contract: period, filters, the trend's metric and bucket, and the open drill-down.
 * Every field is .catch()-guarded so a stale or hand-edited URL drops the bad field instead of throwing.
 */
import { z } from 'zod';

import { Channel, MetricBucket, MetricName, Product } from '../../api/generated/model';
import type { GetMetricsSummaryParams } from '../../api/generated/model';

const isoDate = z.iso.date().optional().catch(undefined);

export const RANGES = ['4w', '13w', '12m', 'custom'] as const;
export type Range = (typeof RANGES)[number];

export const metricsSearchSchema = z.object({
  range: z.enum(RANGES).default('13w').catch('13w'),
  /** Custom range only. */
  from: isoDate,
  to: isoDate,
  product: z.enum(Object.values(Product)).optional().catch(undefined),
  channel: z.enum(Object.values(Channel)).optional().catch(undefined),
  partner: z.number().int().positive().optional().catch(undefined),
  /** false: native data only. */
  legacy: z.boolean().optional().catch(undefined),
  chart: z.enum(Object.values(MetricName)).default('throughput').catch('throughput'),
  bucket: z.enum(Object.values(MetricBucket)).default('week').catch('week'),
  view: z.enum(['chart', 'table']).default('chart').catch('chart'),
  /** The drill-down: which metric, an optional sub-range (a bar), or the open fix-live clocks. */
  drill: z.enum(Object.values(MetricName)).optional().catch(undefined),
  dfrom: isoDate,
  dto: isoDate,
  open: z.boolean().optional().catch(undefined),
});

export type MetricsSearch = z.output<typeof metricsSearchSchema>;

export const SEARCH_DEFAULTS = { range: '13w', chart: 'throughput', bucket: 'week', view: 'chart' } as const;

/** The query every metrics call shares (period + filters). */
export function metricsParams(
  search: MetricsSearch,
  period: { from: string; to: string },
): GetMetricsSummaryParams {
  const params: GetMetricsSummaryParams = { period_from: period.from, period_to: period.to };
  if (search.product !== undefined) params.product = [search.product];
  if (search.channel !== undefined) params.channel = [search.channel];
  if (search.partner !== undefined) params.partner_id = [search.partner];
  if (search.legacy === false) params.include_legacy = false;
  return params;
}

export function hasFilters(search: MetricsSearch): boolean {
  return (
    search.product !== undefined ||
    search.channel !== undefined ||
    search.partner !== undefined ||
    search.legacy === false
  );
}
