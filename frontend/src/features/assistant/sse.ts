/*
 * Server-Sent Events reader for the assistant's run streams. Frames end at a blank line; `:` lines are
 * comments (the server's `: keepalive`); `data:` lines carry one JSON protocol event. `event:` names are
 * redundant with the event's `method`, so they're ignored. The stream's end flushes a final unterminated frame.
 */

function frameData(frame: string): string | undefined {
  const data: string[] = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith('data:')) {
      data.push(line.slice(line.startsWith('data: ') ? 6 : 5));
    }
  }
  return data.length > 0 ? data.join('\n') : undefined;
}

export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let pendingCr = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      // A trailing \r may be half of a \r\n: hold it back until the next chunk shows which.
      let text = pendingCr + chunk;
      pendingCr = text.endsWith('\r') ? '\r' : '';
      if (pendingCr !== '') text = text.slice(0, -1);
      buffer += text.replace(/\r\n?/g, '\n');
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const data = frameData(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (data !== undefined) yield JSON.parse(data) as unknown;
        boundary = buffer.indexOf('\n\n');
      }
    }
    const data = frameData(buffer.trim());
    if (data !== undefined) yield JSON.parse(data) as unknown;
  } finally {
    reader.releaseLock();
  }
}
