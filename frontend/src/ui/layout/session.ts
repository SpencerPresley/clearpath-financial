/*
 * Sign-in and sign-out through allauth headless (browser client, session cookie). Every allauth browser view
 * calls Django's get_token, so a GET of the session endpoint issues the csrftoken cookie that the login POST
 * then echoes (src/api/mutator.ts adds X-CSRFToken on unsafe methods).
 */
import { ApiError, customFetch } from '../../api/mutator';

const SESSION_URL = '/_allauth/browser/v1/auth/session';
const LOGIN_URL = '/_allauth/browser/v1/auth/login';

/** allauth error bodies: { status, errors: [{ message, code, param? }] }. */
function allauthMessage(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null || !('errors' in body)) return undefined;
  const errors = body.errors;
  if (!Array.isArray(errors)) return undefined;
  const first: unknown = errors[0];
  if (typeof first !== 'object' || first === null || !('message' in first)) return undefined;
  return typeof first.message === 'string' ? first.message : undefined;
}

/**
 * Only a 400 is about what was typed. A 403 is CSRF or a firewall in front of the app, a 429 is allauth's
 * throttle, a 5xx is the server: telling someone to recheck a correct password there sends them the wrong way.
 */
function signInRefusal(error: ApiError): string {
  if (error.status === 403) return 'Sign-in was refused by the server (403). Reload the page and try again.';
  if (error.status === 429) return 'Too many sign-in attempts. Wait a few minutes and try again.';
  if (error.status >= 500) return 'The server had a problem. Try again in a minute.';
  if (error.status === 400) {
    return allauthMessage(error.body) ?? 'Couldn’t sign in. Check the email and password.';
  }
  return (
    allauthMessage(error.body) ?? `Couldn’t sign in (${String(error.status)}). Reload the page and try again.`
  );
}

async function ensureCsrfCookie(): Promise<void> {
  try {
    await customFetch(SESSION_URL);
  } catch (error) {
    // 401 is the normal answer when signed out; the response still carries the cookie.
    if (!(error instanceof ApiError)) throw error;
  }
}

export async function signIn(email: string, password: string): Promise<void> {
  await ensureCsrfCookie();
  try {
    await customFetch(LOGIN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) {
        // Authenticated but another step is pending (MFA). Not supported in this UI yet.
        throw new Error('This account needs a second sign-in step, which this app does not support yet.', {
          cause: error,
        });
      }
      throw new Error(signInRefusal(error), { cause: error });
    }
    throw new Error('Can’t reach the server. Check your connection and try again.', { cause: error });
  }
}

export async function signOut(): Promise<void> {
  try {
    await customFetch(SESSION_URL, { method: 'DELETE' });
  } catch (error) {
    // allauth answers a successful logout with 401 (no session left).
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
  }
}
