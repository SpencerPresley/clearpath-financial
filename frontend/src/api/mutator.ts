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

export async function customFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  if (UNSAFE_METHODS.has(method)) {
    const csrfToken = readCookie('csrftoken');
    if (csrfToken !== undefined) {
      headers.set('X-CSRFToken', csrfToken);
    }
  }

  const response = await fetch(url, { ...options, method, headers, credentials: 'same-origin' });
  const body = await parseBody(response);
  if (!response.ok) {
    throw new ApiError(response.status, body);
  }
  return body as T;
}
