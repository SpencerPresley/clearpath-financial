import { describe, expect, it } from 'vitest';

import { readSse } from './sse';

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(chunks: string[]): Promise<unknown[]> {
  const out: unknown[] = [];
  for await (const data of readSse(streamOf(chunks))) out.push(data);
  return out;
}

describe('readSse', () => {
  it('yields the JSON data of each frame in one chunk', async () => {
    expect(await collect(['event: lifecycle\ndata: {"a":1}\n\nevent: values\ndata: {"b":2}\n\n'])).toEqual([
      { a: 1 },
      { b: 2 },
    ]);
  });

  it('joins a frame split across chunks, even mid-line and mid-CRLF', async () => {
    expect(await collect(['event: lifecycle\r\nda', 'ta: {"a"', ':1}\r', '\n\r\n'])).toEqual([{ a: 1 }]);
    expect(await collect(['data: {"a":\r', '\ndata: 1}\r\n\r\n'])).toEqual([{ a: 1 }]);
  });

  it('ignores keepalive comments and frames without data', async () => {
    expect(await collect([': keepalive\n\n', 'data: {"a":1}\n\n', 'event: ping\n\n'])).toEqual([{ a: 1 }]);
  });

  it('joins multi-line data with newlines', async () => {
    expect(await collect(['data: {"text":\ndata: "x"}\n\n'])).toEqual([{ text: 'x' }]);
  });

  it('flushes a trailing frame the server closed without a blank line', async () => {
    expect(await collect(['data: {"a":1}\n\ndata: {"b":2}'])).toEqual([{ a: 1 }, { b: 2 }]);
  });

  it('handles a multibyte character split across chunks', async () => {
    const bytes = new TextEncoder().encode('data: {"t":"é"}\n\n');
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 13));
        controller.enqueue(bytes.slice(13));
        controller.close();
      },
    });
    const out: unknown[] = [];
    for await (const data of readSse(stream)) out.push(data);
    expect(out).toEqual([{ t: 'é' }]);
  });
});
