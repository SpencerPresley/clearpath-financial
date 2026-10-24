import type { ItemRowOut } from '../../api/generated/model';

export function TagsCell({ row }: { row: ItemRowOut }) {
  return (
    <span className="app-tags">
      {row.tags.map((tag) => (
        <span key={tag} className="app-tag">
          {tag}
        </span>
      ))}
    </span>
  );
}
