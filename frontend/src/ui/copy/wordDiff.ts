import { diffArrays } from 'diff';

import type { DiffSegmentOut } from '../../api/generated/model';

// Numbers stay whole ("5.99", "10,000") so a rate change reads as one replacement, not "5" + "." + "99"
// (jsdiff's own word tokenizer splits on punctuation). Then words, whitespace runs, and any other char.
const TOKEN = /\d+(?:[.,]\d+)*|[\p{L}\p{N}'’]+|\s+|./gsu;

function tokenize(text: string): string[] {
  return text.match(TOKEN) ?? [];
}

/**
 * A short run of unchanged text between two changes ("your", "rate", a lone space): a reader sees one
 * rewritten phrase, so it's folded into the change rather than shown as "with ; no checking impact your on".
 */
function isIncidental(text: string): boolean {
  return !text.includes('\n') && text.length <= 8 && text.trim().split(/\s+/).filter(Boolean).length <= 1;
}

/**
 * Client-side word diff in the server's segment shape, for previews of text that isn't a version yet
 * (resubmit, approve with edits). Persisted versions use `GET /items/{id}/diff`.
 */
export function wordDiff(before: string, after: string): DiffSegmentOut[] {
  const changes = diffArrays(tokenize(before), tokenize(after)).map((change) => ({
    op: change.added ? ('insert' as const) : change.removed ? ('delete' as const) : ('equal' as const),
    text: change.value.join(''),
  }));

  const segments: DiffSegmentOut[] = [];
  let removed = '';
  let added = '';
  const flush = () => {
    if (removed !== '') segments.push({ op: 'delete', text: removed });
    if (added !== '') segments.push({ op: 'insert', text: added });
    removed = '';
    added = '';
  };

  changes.forEach((change, index) => {
    if (change.op === 'delete') {
      removed += change.text;
    } else if (change.op === 'insert') {
      added += change.text;
    } else {
      const inChange = removed !== '' || added !== '';
      const changeFollows = changes[index + 1] !== undefined;
      if (inChange && changeFollows && isIncidental(change.text)) {
        removed += change.text;
        added += change.text;
        return;
      }
      flush();
      segments.push({ op: 'equal', text: change.text });
    }
  });
  flush();
  return segments;
}
