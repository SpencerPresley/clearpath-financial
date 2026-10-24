/*
 * Edit an item's tags: chips with remove buttons plus an input that adds on Enter. Each change is saved at
 * once (optimistic, see useItemPatch), so there is no Save button. Limits match the API: 1-50 characters.
 */
import { useState } from 'react';
import { Input, TextField } from 'react-aria-components';

import { IconButton } from '../../ui/IconButton';

export const TAG_MAX = 50;

export function TagEditor({
  tags,
  onChange,
  autoFocus = true,
}: {
  tags: readonly string[];
  onChange: (tags: string[]) => void;
  autoFocus?: boolean;
}) {
  const [draft, setDraft] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  const add = () => {
    const tag = draft.trim();
    if (tag === '') return;
    if (tag.length > TAG_MAX) {
      setProblem(`Tags are ${String(TAG_MAX)} characters or fewer.`);
      return;
    }
    setProblem(null);
    setDraft('');
    if (!tags.includes(tag)) onChange([...tags, tag]);
  };

  return (
    <div className="app-tag-editor">
      {tags.length > 0 && (
        <ul className="app-tags flex-wrap" aria-label="Tags">
          {tags.map((tag) => (
            <li key={tag} className="app-tag pr-0.5">
              {tag}
              <IconButton
                icon="action.close"
                size="sm"
                tooltip={false}
                aria-label={`Remove tag ${tag}`}
                className="app-tag-remove"
                onPress={() => {
                  onChange(tags.filter((t) => t !== tag));
                }}
              />
            </li>
          ))}
        </ul>
      )}
      <TextField
        aria-label="Add tag"
        value={draft}
        onChange={(value) => {
          setDraft(value);
          if (problem !== null) setProblem(null);
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            add();
          }
        }}
        isInvalid={problem !== null}
        autoFocus={autoFocus}
      >
        <Input className="app-input" placeholder="Add tag, press Enter" />
      </TextField>
      {problem !== null && (
        <p role="alert" className="app-field-error">
          {problem}
        </p>
      )}
    </div>
  );
}
