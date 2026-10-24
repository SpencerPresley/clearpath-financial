import { http, HttpResponse } from 'msw';

import { getListDecisionsMockHandler } from '../../api/generated/decisions/decisions.msw';
import {
  getGetItemHistoryMockHandler,
  getGetItemMockHandler,
  getListCommentsMockHandler,
  getListItemAttachmentsMockHandler,
  getListPlacementsMockHandler,
  getListVersionsMockHandler,
} from '../../api/generated/items/items.msw';
import type {
  AttachmentOut,
  CommentOut,
  DecisionOut,
  FindingOut,
  ItemDetailOut,
  ItemHistoryOut,
  PlacementOut,
} from '../../api/generated/model';
import { wordDiff } from '../../ui/copy/wordDiff';
import {
  ATTACHMENTS,
  COMMENTS,
  FINDINGS_OPEN,
  HISTORY,
  PLACEMENTS,
  itemFixture,
  versionFixture,
} from './review';

export interface ReviewHandlerOptions {
  item?: ItemDetailOut;
  /** Findings by version n; defaults to FINDINGS_OPEN on the current version and none elsewhere. */
  findings?: FindingOut[] | Record<number, FindingOut[]>;
  comments?: CommentOut[];
  attachments?: AttachmentOut[];
  history?: ItemHistoryOut;
  decisions?: DecisionOut[];
  placements?: PlacementOut[];
}

/** Read handlers for one item's review screen, built on the generated MSW handlers. */
export function reviewHandlers(options: ReviewHandlerOptions = {}) {
  const item = options.item ?? itemFixture();
  const current = item.current_version_n ?? 1;
  const findings = options.findings ?? FINDINGS_OPEN;
  const findingsFor = (n: number): FindingOut[] =>
    Array.isArray(findings) ? (n === current ? findings : []) : (findings[n] ?? []);
  const versionText = (n: number): string =>
    n === current && item.current_version !== null
      ? item.current_version.content_text
      : versionFixture(n === 1 ? 1 : 2).content_text;

  return [
    getGetItemMockHandler(item),
    http.get('*/api/items/:itemId/findings', ({ request }) => {
      const n = Number(new URL(request.url).searchParams.get('version_n') ?? current);
      return HttpResponse.json(findingsFor(n));
    }),
    getListCommentsMockHandler(options.comments ?? COMMENTS),
    getListItemAttachmentsMockHandler(options.attachments ?? ATTACHMENTS),
    getGetItemHistoryMockHandler(options.history ?? HISTORY),
    getListDecisionsMockHandler(
      options.decisions ?? (item.latest_decision === null ? [] : [item.latest_decision]),
    ),
    getListPlacementsMockHandler(options.placements ?? (item.live_placements_count > 0 ? PLACEMENTS : [])),
    getListVersionsMockHandler(item.versions),
    http.get('*/api/items/:itemId/versions/:n', ({ params }) => {
      const n = Number(params.n);
      const summary = item.versions.find((v) => v.n === n);
      if (summary === undefined) {
        return HttpResponse.json(
          { code: 'not_found', message: `Version ${String(n)} not found.` },
          { status: 404 },
        );
      }
      return HttpResponse.json({
        ...versionFixture(n === 1 ? 1 : 2),
        ...summary,
        content_text: versionText(n),
      });
    }),
    http.get('*/api/items/:itemId/diff', ({ request }) => {
      const params = new URL(request.url).searchParams;
      const fromN = Number(params.get('from_n'));
      const toN = Number(params.get('to_n'));
      return HttpResponse.json({
        from_n: fromN,
        to_n: toN,
        segments: wordDiff(versionText(fromN), versionText(toN)),
      });
    }),
  ];
}
