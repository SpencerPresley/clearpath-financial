import { useMemo } from 'react';

import { useGetVersionDiff } from '../../api/generated/items/items';
import type {
  AttachmentOut,
  FindingDraftOut,
  FindingOut,
  ItemDetailOut,
  VersionOut,
} from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { CopyEditor } from '../../ui/copy/CopyEditor';
import { DiffText, countChanges } from '../../ui/copy/DiffText';
import { HighlightedText } from '../../ui/copy/HighlightedText';
import { FindingSummary } from '../../ui/findings/FindingSummary';
import { marksFromFindings } from '../../ui/copy/marks';
import type { SpanMark } from '../../ui/copy/segments';
import { wordDiff } from '../../ui/copy/wordDiff';
import { SelectField } from '../../ui/forms/fields';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { Icon } from '../../ui/Icon';
import { ORIGIN_LABELS, plural } from '../../ui/labels';
import { SkeletonText } from '../../ui/Skeleton';
import { findingMessageId } from './FindingCard';

export interface EditState {
  text: string;
  onChange: (text: string) => void;
  marks: SpanMark[];
  /** Live code findings on the edited text: open ones on the new version block the approval. */
  findings: FindingDraftOut[];
  checking: boolean;
  showDiff: boolean;
  onShowDiffChange: (show: boolean) => void;
}

export interface CopyPaneProps {
  item: ItemDetailOut;
  version: VersionOut | undefined;
  versionLoading: boolean;
  shownN: number;
  compareN: number | undefined;
  findings: readonly FindingOut[];
  activeId: number | null;
  attachments: readonly AttachmentOut[];
  onActivate: (id: number) => void;
  onVersionChange: (n: number) => void;
  onCompareChange: (n: number | undefined) => void;
  /** Present while the reviewer is writing their edited version (Approve with edits). */
  edit?: EditState;
}

function CopySkeleton() {
  return (
    <div role="status" aria-label="Loading copy" className="app-copy-skeleton">
      {['92%', '84%', '96%', '60%', '88%'].map((width) => (
        <SkeletonText key={width} width={width} />
      ))}
    </div>
  );
}

function versionLabel(item: ItemDetailOut, n: number): string {
  const summary = item.versions.find((v) => v.n === n);
  if (summary === undefined) {
    return `v${String(n)}`;
  }
  const current = n === item.current_version_n ? ' · current' : '';
  return `v${String(n)} · ${ORIGIN_LABELS[summary.origin]} · ${summary.author.name}${current}`;
}

function CompareView({ itemId, fromN, toN }: { itemId: number; fromN: number; toN: number }) {
  const diff = useGetVersionDiff(itemId, { from_n: fromN, to_n: toN });
  if (diff.isPending) {
    return <CopySkeleton />;
  }
  if (diff.isError) {
    return (
      <p className="app-inline-error" role="alert">
        Couldn’t load the comparison. {apiErrorMessage(diff.error)}
      </p>
    );
  }
  const changes = countChanges(diff.data.segments);
  return (
    <>
      <p className="app-copy-caption">
        Changes from v{fromN} to v{toN}: {changes === 0 ? 'none' : plural(changes, 'change')}
      </p>
      <DiffText segments={diff.data.segments} />
    </>
  );
}

function Mockup({ attachments }: { attachments: readonly AttachmentOut[] }) {
  const image = attachments.find((a) => a.kind === 'creative' && a.content_type.startsWith('image/'));
  if (image === undefined) {
    return null;
  }
  return (
    <figure className="app-mockup">
      <img
        src={image.download_url}
        alt={`Mockup: ${image.original_name}`}
        className="app-mockup-image"
        loading="lazy"
      />
      <figcaption className="app-copy-caption">Mockup · {image.original_name}</figcaption>
    </figure>
  );
}

/** The center of the review screen: the copy under review, its flagged spans, version compare, mockup. */
export function CopyPane({
  item,
  version,
  versionLoading,
  shownN,
  compareN,
  findings,
  activeId,
  attachments,
  onActivate,
  onVersionChange,
  onCompareChange,
  edit,
}: CopyPaneProps) {
  const text = version?.content_text ?? '';
  const marks = useMemo(() => marksFromFindings(text, findings), [text, findings]);
  const versionOptions = [...item.versions]
    .sort((a, b) => b.n - a.n)
    .map((v) => ({ id: String(v.n), label: versionLabel(item, v.n) }));
  const compareOptions = [
    { id: 'none', label: 'No comparison' },
    ...versionOptions
      .filter((o) => o.id !== String(shownN))
      .map((o) => ({ ...o, label: `Compare with ${o.label}` })),
  ];

  let body;
  if (edit !== undefined) {
    const segments = edit.showDiff ? wordDiff(text, edit.text) : null;
    body = (
      <div className="app-edit-pane">
        <div className="app-copy-toolbar">
          <span className="app-copy-caption">
            <Icon name="action.edit" size={14} /> Your edit becomes v{(item.current_version_n ?? 0) + 1},
            authored by you, and is the version approved.
          </span>
          <Button
            size="sm"
            variant="ghost"
            onPress={() => {
              edit.onShowDiffChange(!edit.showDiff);
            }}
          >
            {edit.showDiff ? 'Back to editing' : `Changes vs v${String(shownN)}`}
          </Button>
        </div>
        {segments === null ? (
          <>
            <CopyEditor
              label={`Edited copy (v${String((item.current_version_n ?? 0) + 1)})`}
              hideLabel
              value={edit.text}
              onChange={edit.onChange}
              marks={edit.marks}
              autoFocus
              description={edit.checking ? 'Checking…' : 'Code checks run as you type.'}
            />
            {edit.findings.length > 0 && (
              <section className="app-edit-findings" aria-labelledby="edit-findings-title">
                <h3 id="edit-findings-title" className="app-panel-heading">
                  {plural(edit.findings.length, 'code finding')} in your edit
                  <span className="app-muted">
                    {' '}
                    · findings not dismissed before come back open on v{(item.current_version_n ?? 0) + 1}
                  </span>
                </h3>
                {edit.findings.map((finding) => (
                  <FindingSummary
                    key={`${finding.rule_id}-${String(finding.span?.start ?? 'none')}`}
                    severity={finding.severity}
                    source={finding.source}
                    message={finding.message}
                    citation={finding.citation}
                    quote={finding.quote}
                  />
                ))}
              </section>
            )}
          </>
        ) : (
          <>
            <p className="app-copy-caption">
              {countChanges(segments) === 0 ? 'No edits yet' : plural(countChanges(segments), 'change')}
            </p>
            <DiffText segments={segments} className="app-copy-sheet" />
          </>
        )}
      </div>
    );
  } else if (versionLoading || version === undefined) {
    body = <CopySkeleton />;
  } else if (compareN !== undefined) {
    body = (
      <div className="app-copy-sheet">
        <CompareView itemId={item.id} fromN={Math.min(compareN, shownN)} toN={Math.max(compareN, shownN)} />
      </div>
    );
  } else {
    body = (
      <HighlightedText
        className="app-copy-sheet"
        text={text}
        marks={marks}
        activeId={activeId === null ? null : String(activeId)}
        describedByPrefix={findingMessageId('')}
        onMarkPress={(id) => {
          onActivate(Number(id));
        }}
      />
    );
  }

  return (
    <section className="app-review-center" aria-label="Copy">
      {edit === undefined && (
        <div className="app-copy-toolbar">
          <SelectField
            label="Version"
            hideLabel
            size="sm"
            className="app-version-select"
            value={String(shownN)}
            onChange={(value) => {
              if (value !== null) onVersionChange(Number(value));
            }}
            options={versionOptions}
          />
          {item.versions.length > 1 && (
            <SelectField
              label="Compare"
              hideLabel
              size="sm"
              className="app-version-select"
              value={compareN === undefined ? 'none' : String(compareN)}
              onChange={(value) => {
                onCompareChange(value === null || value === 'none' ? undefined : Number(value));
              }}
              options={compareOptions}
            />
          )}
          {compareN === undefined && marks.length > 0 && (
            <span className="app-copy-legend" aria-hidden="true">
              <span className="app-mark" data-severity="blocking" data-source="code">
                Blocking
              </span>
              <span className="app-mark" data-severity="warning" data-source="code">
                Warning
              </span>
              <span className="app-legend-sep">·</span>
              <span className="app-legend-line" data-source="code">
                Code
              </span>
              <span className="app-legend-line" data-source="llm">
                AI
              </span>
            </span>
          )}
        </div>
      )}
      {body}
      {edit === undefined && <Mockup attachments={attachments} />}
    </section>
  );
}
