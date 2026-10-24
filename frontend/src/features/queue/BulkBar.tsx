/*
 * Bulk actions on the selection (decisions.md "Ergonomics": bulk assign and bulk fast-track approval).
 * - Assign: leads and admins (decisions.md "Who can reassign"), via POST /items/bulk/assign.
 * - Fast-track approve: leads only (the server refuses anyone else), only for selected rows the server marks
 *   `fast_track_eligible`, each at the version its row showed (`seen_versions`); needs a reason. The server skips
 *   any item with open findings (spec §4.2 ruling 4) or a newer version; those, and the selected rows that weren't
 *   eligible, stay selected so they can go the normal lane.
 * An action the viewer can't take isn't rendered (no dead buttons).
 */
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  Button as AriaButton,
  Dialog,
  Heading,
  Label,
  Menu,
  MenuItem,
  MenuTrigger,
  Modal,
  ModalOverlay,
  Popover,
  TextArea,
  TextField,
} from 'react-aria-components';

import { useBulkFastTrackApprove } from '../../api/generated/decisions/decisions';
import {
  getGetQueueStatsQueryKey,
  getListItemsQueryKey,
  useBulkAssignItems,
} from '../../api/generated/items/items';
import type { BulkResultOut, ItemRowOut } from '../../api/generated/model';
import { useListUsers } from '../../api/generated/users/users';
import { PickerName, pickerText } from '../../ui/Availability';
import { Button } from '../../ui/Button';
import { errorMessage } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import type { Viewer } from '../../ui/layout/Viewer';
import { showToast } from '../../ui/toast';
import { Tooltip } from '../../ui/Tooltip';

/**
 * Whether the fast-track lane would take a row: the server computes `fast_track_eligible` with the rule it
 * enforces (a re-review whose current version the offer-terms fan-out generated, with no live page showing other
 * copy), so the bar never guesses from the reopen reason. Open findings and the AI check still decide per item.
 */
export function canFastTrackRow(row: ItemRowOut): boolean {
  return row.fast_track_eligible && row.current_version_n !== null;
}

const NO_FAST_TRACK =
  'None of the selected items can be fast-tracked: only an offer-terms re-review whose live page shows the approved copy can.';

function items(n: number) {
  return `${String(n)} item${n === 1 ? '' : 's'}`;
}

function skippedDetail(result: BulkResultOut): string {
  return result.skipped
    .slice(0, 3)
    .map((s) => s.message)
    .join(' · ');
}

export interface BulkBarProps {
  viewer: Viewer;
  selectedIds: readonly number[];
  /** Loaded rows, to know which selected items are re-reviews. */
  rows: readonly ItemRowOut[];
  /** Replace the selection (cleared on success; skipped items stay). */
  onSelectionChange: (ids: number[]) => void;
}

export function BulkBar({ viewer, selectedIds, rows, onSelectionChange }: BulkBarProps) {
  const qc = useQueryClient();
  const isLead = viewer.roles.includes('lead');
  const canAssign = isLead || viewer.roles.includes('admin');
  const reviewers = useListUsers({ role: 'reviewer' }, { query: { enabled: canAssign } });
  const assign = useBulkAssignItems();
  const fastTrack = useBulkFastTrackApprove();
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reason, setReason] = useState('');

  const selected = new Set(selectedIds);
  // Each re-review at the version its row showed: one a later terms change generated after the queue loaded is
  // skipped as stale_version, never approved unseen.
  const seenVersions = rows.flatMap((r) =>
    selected.has(r.id) && canFastTrackRow(r) && r.current_version_n !== null
      ? [{ item_id: r.id, version_n: r.current_version_n }]
      : [],
  );
  const fastTrackIds = seenVersions.map((v) => v.item_id);
  const fastTrackable = fastTrackIds.length > 0;
  const hasRereview = rows.some((r) => selected.has(r.id) && r.status === 'needs_rereview');

  const settle = () => {
    void qc.invalidateQueries({ queryKey: getListItemsQueryKey().slice(0, 1) });
    void qc.invalidateQueries({ queryKey: getGetQueueStatsQueryKey() });
  };

  const keepSkipped = (result: BulkResultOut) => {
    const skipped = new Set(result.skipped.map((s) => s.item_id));
    onSelectionChange(selectedIds.filter((id) => skipped.has(id)));
  };

  const doAssign = (assigneeId: number | null, name: string) => {
    const ids = [...selectedIds];
    assign.mutate(
      { data: { item_ids: ids, assignee_id: assigneeId } },
      {
        onSuccess: (result) => {
          keepSkipped(result);
          const done = result.succeeded.length;
          if (result.skipped.length === 0) {
            showToast({
              title:
                assigneeId === null
                  ? `Moved ${items(done)} to Unassigned`
                  : `Assigned ${items(done)} to ${name}`,
            });
          } else {
            showToast(
              {
                title: `Assigned ${String(done)} of ${items(ids.length)} · ${String(result.skipped.length)} skipped`,
                description: skippedDetail(result),
              },
              10_000,
            );
          }
        },
        onError: (error) => {
          showToast({
            tone: 'error',
            title: "Couldn't assign the selection",
            description: errorMessage(error, 'Nothing was changed. Try again.'),
          });
        },
        onSettled: settle,
      },
    );
  };

  const doFastTrack = () => {
    const sent = new Set(fastTrackIds);
    fastTrack.mutate(
      { data: { item_ids: fastTrackIds, reason: reason.trim(), seen_versions: seenVersions } },
      {
        onSuccess: (result) => {
          setReasonOpen(false);
          setReason('');
          const skipped = new Set(result.skipped.map((s) => s.item_id));
          onSelectionChange(selectedIds.filter((id) => skipped.has(id) || !sent.has(id)));
          const done = result.succeeded.length;
          showToast(
            result.skipped.length === 0
              ? { title: `Fast-tracked ${items(done)}` }
              : {
                  title: `Fast-tracked ${String(done)} of ${items(fastTrackIds.length)} · ${String(result.skipped.length)} skipped`,
                  description: skippedDetail(result),
                },
            result.skipped.length === 0 ? undefined : 10_000,
          );
        },
        onError: (error) => {
          showToast({
            tone: 'error',
            title: "Couldn't fast-track the selection",
            description: errorMessage(error, 'Nothing was approved. Try again.'),
          });
        },
        onSettled: settle,
      },
    );
  };

  return (
    <div className="app-bulk-bar" role="toolbar" aria-label="Bulk actions">
      <span className="app-bulk-count app-figure">{`${String(selectedIds.length)} selected`}</span>
      {canAssign && (
        <MenuTrigger>
          <AriaButton
            className="app-btn"
            data-variant="secondary"
            data-size="sm"
            isDisabled={assign.isPending}
          >
            <Icon name="action.assign" size={14} />
            Assign…
          </AriaButton>
          <Popover className="app-popover max-h-80 overflow-auto" placement="bottom start" offset={4}>
            <Menu
              className="app-menu"
              aria-label="Assign to"
              onAction={(key) => {
                if (key === 'none') {
                  doAssign(null, 'Unassigned');
                  return;
                }
                const user = reviewers.data?.find((u) => String(u.id) === key);
                if (user !== undefined) doAssign(user.id, user.display_name);
              }}
            >
              <MenuItem id="none" className="app-menu-item">
                Unassigned
              </MenuItem>
              {(reviewers.data ?? []).map((user) => (
                <MenuItem
                  key={user.id}
                  id={String(user.id)}
                  textValue={pickerText(user.display_name, user.is_available)}
                  className="app-menu-item"
                >
                  <PickerName name={user.display_name} isAvailable={user.is_available} />
                </MenuItem>
              ))}
            </Menu>
          </Popover>
        </MenuTrigger>
      )}
      {isLead && hasRereview && (
        <span className="app-bulk-action">
          <Button
            size="sm"
            icon="action.approve"
            isDisabled={!fastTrackable}
            aria-describedby={fastTrackable ? undefined : 'bulk-fast-track-why'}
            onPress={() => {
              setReasonOpen(true);
            }}
          >
            {fastTrackable
              ? `Fast-track ${String(fastTrackIds.length)} ${fastTrackIds.length === 1 ? 're-review' : 're-reviews'}…`
              : 'Fast-track'}
          </Button>
          {!fastTrackable && (
            <>
              {/* A disabled button gets no hover, so the reason sits on its own trigger (and for screen readers). */}
              <Tooltip content={NO_FAST_TRACK} delay={200}>
                <AriaButton className="app-pack-why" aria-label="Why fast-track is off">
                  <Icon name="feedback.info" size={14} />
                </AriaButton>
              </Tooltip>
              <span id="bulk-fast-track-why" className="sr-only">
                {NO_FAST_TRACK}
              </span>
            </>
          )}
        </span>
      )}
      <Button
        size="sm"
        variant="ghost"
        onPress={() => {
          onSelectionChange([]);
        }}
      >
        Clear selection
      </Button>

      <ModalOverlay
        isOpen={reasonOpen}
        onOpenChange={setReasonOpen}
        isDismissable
        className="app-modal-overlay"
      >
        <Modal className="app-modal w-96">
          <Dialog className="flex flex-col gap-3 outline-none">
            <Heading slot="title" className="text-sm font-semibold">
              {`Fast-track approve ${items(fastTrackIds.length)}`}
            </Heading>
            <p className="text-muted">
              Approves the generated version of each re-review. Items with open findings are skipped and stay
              selected.
            </p>
            <TextField value={reason} onChange={setReason} isRequired maxLength={2000} autoFocus>
              <Label className="mb-1 block text-meta font-medium">Reason</Label>
              <TextArea className="app-textarea" />
            </TextField>
            <div className="flex justify-end gap-2">
              <Button
                size="sm"
                variant="ghost"
                onPress={() => {
                  setReasonOpen(false);
                }}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                variant="primary"
                isDisabled={reason.trim() === '' || fastTrack.isPending}
                onPress={doFastTrack}
              >
                Fast-track approve
              </Button>
            </div>
          </Dialog>
        </Modal>
      </ModalOverlay>
    </div>
  );
}
