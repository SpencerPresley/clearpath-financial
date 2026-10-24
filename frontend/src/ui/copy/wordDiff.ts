import { diffArrays } from 'diff';

import type { DiffSegmentOut } from '../../api/generated/model';

// Numbers stay whole ("5.99", "10,000") so a rate change reads as one replacement, not "5" + "." + "99"
// (jsdiff's own word tokenizer splits on punctuation). Then words, whitespace runs, and any other char.
const TOKEN = /\d+(?:[.,]\d+)*|[\p{L}\p{N}'’]+|\s+|./gsu;

function tokenize(text: string): string[] {
  return text.match(TOKEN) ?? [];
}

/**
 * Client-side word diff in the server's segment shape, for previews of text that isn't a version yet
 * (resubmit, approve with edits). Persisted versions use `GET /items/{id}/diff`.
 */
export function wordDiff(before: string, after: string): DiffSegmentOut[] {
  const segments: DiffSegmentOut[] = [];
  for (const change of diffArrays(tokenize(before), tokenize(after))) {
    const op = change.added ? 'insert' : change.removed ? 'delete' : 'equal';
    const text = change.value.join('');
    const last = segments[segments.length - 1];
    if (last?.op === op) {
      last.text += text;
    } else {
      segments.push({ op, text });
    }
  }
  return segments;
}
