// The single HTTP entry point for generated API hooks. Same-origin session auth:
// the browser sends the Django session cookie, and unsafe methods echo the
// csrftoken cookie back in the X-CSRFToken header.

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`API request failed with status ${String(status)}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

export function readCookie(name: string): string | undefined {
  const prefix = `${name}=`;
  const match = document.cookie.split('; ').find((part) => part.startsWith(prefix));
  return match === undefined ? undefined : decodeURIComponent(match.slice(prefix.length));
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204 || response.status === 205) {
    return undefined;
  }
  const contentType = response.headers.get('content-type') ?? '';
  return contentType.includes('application/json') ? response.json() : response.text();
}

function sameOriginFetch(url: string, options: RequestInit): Promise<Response> {
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  if (UNSAFE_METHODS.has(method)) {
    const csrfToken = readCookie('csrftoken');
    if (csrfToken !== undefined) {
      headers.set('X-CSRFToken', csrfToken);
    }
  }
  return fetch(url, { ...options, method, headers, credentials: 'same-origin' });
}

export async function customFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await sameOriginFetch(url, options);
  const body = await parseBody(response);
  if (!response.ok) {
    throw new ApiError(response.status, body);
  }
  return body as T;
}

/**
 * For streaming responses (the assistant's SSE runs): same auth as customFetch, but resolves with the
 * Response once headers arrive and leaves a 2xx body unread for the caller to stream. Non-2xx bodies are
 * JSON errors sent before the stream starts, so they still throw ApiError with the parsed body.
 */
export async function streamFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const response = await sameOriginFetch(url, init);
  if (!response.ok) {
    throw new ApiError(response.status, await parseBody(response));
  }
  return response;
}
