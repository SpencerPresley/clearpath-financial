/*
 * A search snippet: the server sends structured parts (foundation report: ts_headline doesn't escape untrusted
 * affiliate copy), and the matched words render as <mark> text nodes. Never HTML.
 */
import type { SnippetPartOut } from '../api/generated/model';

export function SnippetText({ parts }: { parts: readonly SnippetPartOut[] }) {
  return (
    <span className="app-snippet">
      {parts.map((part, index) =>
        part.highlighted ? (
          <mark key={index} className="app-snippet-mark">
            {part.text}
          </mark>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </span>
  );
}
