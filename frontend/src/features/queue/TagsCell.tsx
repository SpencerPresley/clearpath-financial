import { Button as AriaButton, Dialog, DialogTrigger, Popover } from 'react-aria-components';

import type { ItemRowOut } from '../../api/generated/model';
import { useQueueCell } from './cellContext';
import { stopRowClick } from './stopRowClick';
import { TagEditor } from './TagEditor';

function TagList({ tags }: { tags: readonly string[] }) {
  return (
    <span className="app-tags">
      {tags.map((tag) => (
        <span key={tag} className="app-tag">
          {tag}
        </span>
      ))}
    </span>
  );
}

/** Tags: read-only chips, or for the submitter and reviewers a button that opens the tag editor. */
export function TagsCell({ row }: { row: ItemRowOut }) {
  const { canEditTags, save, activeId } = useQueueCell();
  if (!canEditTags(row)) return <TagList tags={row.tags} />;

  const summary = row.tags.length > 0 ? row.tags.join(', ') : 'none';
  return (
    <span className="app-cell-control" onClick={stopRowClick}>
      <DialogTrigger>
        <AriaButton
          className="app-cell-edit app-cell-edit-wide"
          aria-label={`Tags for ${row.key}: ${summary}. Edit`}
          excludeFromTabOrder={row.id !== activeId}
        >
          {row.tags.length > 0 ? (
            <TagList tags={row.tags} />
          ) : (
            <span className="app-cell-edit-hint">Add tag</span>
          )}
        </AriaButton>
        <Popover className="app-popover w-72 p-2" placement="bottom start" offset={4}>
          <Dialog aria-label={`Tags for ${row.key}`} className="outline-none">
            <TagEditor
              tags={row.tags}
              onChange={(tags) => {
                save(row, { tags });
              }}
            />
          </Dialog>
        </Popover>
      </DialogTrigger>
    </span>
  );
}
