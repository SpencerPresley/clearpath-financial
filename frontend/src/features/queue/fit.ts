/*
 * Fitting the queue's columns to the width the table actually has (walkthrough-1 nit 3). The region narrows
 * when the preview drawer or the assistant opens, or the window is 1280px: first every column tightens to its
 * content (badges, names truncate), then columns step aside lowest-priority first, and the title keeps what's
 * left. Risk and Assignee never step aside: they are what a reviewer triages by. Widths someone dragged always
 * win. This is layout configuration only; columns.tsx keeps the designed defaults and the cell renderers.
 */
import { queueColumns, TITLE_MIN_WIDTH } from './columns';
import type { ColumnId, ColumnSizing, ColumnVisibility } from './columns';

/**
 * Below this much title, the designed widths give way to the compact ones. 300 keeps the designed widths at
 * 1440 with or without a classic 15px scrollbar (Windows, most Linux), so the hosted demo matches macOS there.
 */
const COMFORTABLE_TITLE = 300;
/** Columns step aside until the title gets at least this much. */
const TITLE_TARGET = 200;

/**
 * Tight but whole: each width fits the column's widest content in the seeded demo (status "Changes requested",
 * the risk picker, an avatar plus a short name) and its header with the sort glyph. Select is 40px so the
 * row checkbox's hit area is 40px wide.
 */
const COMPACT: Partial<Record<ColumnId, number>> = {
  select: 40,
  key: 72,
  status: 144,
  risk_tier: 96,
  product: 112,
  channel: 104,
  partner: 112,
  assignee: 112,
  open_findings: 72,
  age: 56,
  round: 68,
  reopen_reason: 128,
  tags: 160,
  notes: 180,
};

/** At every width: the select cell is the row checkbox's hit area, so it is 40px wide (WCAG 2.5.8). */
const ALWAYS: Partial<Record<ColumnId, number>> = { select: 40 };

/** Last resort when even the protected columns crowd the title (1280 with the drawer open). */
const TIGHTEST: Partial<Record<ColumnId, number>> = { assignee: 92 };

/**
 * Lowest priority first. Chosen extras go before the defaults; the drawer and the review screen show partner,
 * round, findings and age for the item in hand.
 */
const STEP_ASIDE: readonly ColumnId[] = [
  'notes',
  'tags',
  'reopen_reason',
  'channel',
  'product',
  'round',
  'partner',
  'open_findings',
  'age',
];

/** The table never draws a column below its minSize (columns.tsx), so neither does the arithmetic. */
const LIMITS = new Map(queueColumns.map((c) => [c.id ?? '', { size: c.size ?? 120, min: c.minSize ?? 0 }]));

/** The width of every shown column except the title, which takes the rest. */
export function fixedWidth(visibility: ColumnVisibility, sizing: ColumnSizing): number {
  return queueColumns
    .map((c) => c.id as ColumnId)
    .filter((id) => id !== 'title' && visibility[id] !== false)
    .reduce((sum, id) => {
      const limits = LIMITS.get(id) ?? { size: 120, min: 0 };
      return sum + Math.max(sizing[id] ?? limits.size, limits.min);
    }, 0);
}

function over(base: Partial<Record<ColumnId, number>>, user: ColumnSizing): ColumnSizing {
  return { ...(base as ColumnSizing), ...user };
}

export interface Fit {
  visibility: ColumnVisibility;
  /** Widths for the table: the compact layout under the user's own; empty means the designed widths. */
  sizing: ColumnSizing;
}

/** `available`: the table region's inner width, or null before it has been measured. */
export function fitColumns(available: number | null, visibility: ColumnVisibility, user: ColumnSizing): Fit {
  const designed = over(ALWAYS, user);
  if (available === null || fixedWidth(visibility, designed) + COMFORTABLE_TITLE <= available) {
    return { visibility, sizing: designed };
  }
  let sizing = over(COMPACT, user);
  const shown = { ...visibility };
  for (const id of STEP_ASIDE) {
    if (fixedWidth(shown, sizing) + TITLE_TARGET <= available) break;
    if (shown[id] !== false) shown[id] = false;
  }
  if (fixedWidth(shown, sizing) + TITLE_MIN_WIDTH > available) {
    sizing = over({ ...COMPACT, ...TIGHTEST }, user);
  }
  return { visibility: shown, sizing };
}
