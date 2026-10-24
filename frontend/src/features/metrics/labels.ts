import type { MetricName } from '../../api/generated/model';

export interface MetricMeta {
  label: string;
  /** Unit of the trend's y axis and the drill-down's value column. */
  unit: 'hours' | 'rounds' | 'decisions';
  /** What one drill-down row is. */
  noun: [one: string, many: string];
  /** The definition, one line, shown under the tile and on the drill-down. */
  definition: string;
  /** What the imported tracker can contribute, when it differs from native data. */
  importedNote?: string;
}

export const METRIC_META: Record<MetricName, MetricMeta> = {
  time_to_first_review: {
    label: 'Time to first review',
    unit: 'hours',
    noun: ['item', 'items'],
    definition: 'Submitted to a reviewer starting on it.',
    importedNote: 'Imported: submitted to the first reviewer comment, day precision.',
  },
  time_per_round: {
    label: 'Time per round',
    unit: 'hours',
    noun: ['round', 'rounds'],
    definition: 'Each submission to its decision.',
    importedNote: 'Native only: the tracker has no per-round dates.',
  },
  rounds_per_item: {
    label: 'Rounds per item',
    unit: 'rounds',
    noun: ['decided item', 'decided items'],
    definition: 'Rounds until approved or rejected.',
  },
  time_to_fix_live: {
    label: 'Time to fix live content',
    unit: 'hours',
    noun: ['re-review', 're-reviews'],
    definition: 'Live content sent back, to approved again or taken down.',
    importedNote: 'Native only: imported items are never re-reviewed.',
  },
  throughput: {
    label: 'Throughput',
    unit: 'decisions',
    noun: ['decision', 'decisions'],
    definition: 'Decisions recorded, every outcome.',
    importedNote: 'Imported: the final decision only.',
  },
};

export const METRIC_ORDER: readonly MetricName[] = [
  'time_to_first_review',
  'time_per_round',
  'rounds_per_item',
  'time_to_fix_live',
  'throughput',
];
