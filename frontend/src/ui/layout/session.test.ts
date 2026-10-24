import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { server } from '../../test/server';
import { signIn } from './session';

const LOGIN = '*/_allauth/browser/v1/auth/login';

function loginAnswers(response: () => Response) {
  server.use(
    http.get('*/_allauth/browser/v1/auth/session', () => HttpResponse.json({ status: 401 }, { status: 401 })),
    http.post(LOGIN, response),
  );
}

describe('signIn errors say which side failed', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=abc';
  });

  it("keeps allauth's own message for bad credentials (400)", async () => {
    loginAnswers(() =>
      HttpResponse.json(
        {
          status: 400,
          errors: [{ message: 'The email address and/or password you specified are not correct.' }],
        },
        { status: 400 },
      ),
    );
    await expect(signIn('a@b.c', 'x')).rejects.toThrow(
      'The email address and/or password you specified are not correct.',
    );
  });

  it('falls back to checking the email and password on a 400 without a message', async () => {
    loginAnswers(() => HttpResponse.json({ status: 400 }, { status: 400 }));
    await expect(signIn('a@b.c', 'x')).rejects.toThrow('Couldn’t sign in. Check the email and password.');
  });

  it('a 403 (CSRF or a firewall) is the server refusing, not a wrong password', async () => {
    loginAnswers(() => new HttpResponse('<h1>Forbidden (403)</h1>', { status: 403 }));
    await expect(signIn('a@b.c', 'x')).rejects.toThrow(
      'Sign-in was refused by the server (403). Reload the page and try again.',
    );
  });

  it('a 429 says to wait', async () => {
    loginAnswers(() => HttpResponse.json({ status: 429 }, { status: 429 }));
    await expect(signIn('a@b.c', 'x')).rejects.toThrow(
      'Too many sign-in attempts. Wait a few minutes and try again.',
    );
  });

  it.each([500, 502, 503])('a %i is a server problem', async (status) => {
    loginAnswers(() => new HttpResponse('upstream', { status }));
    await expect(signIn('a@b.c', 'x')).rejects.toThrow('The server had a problem. Try again in a minute.');
  });

  it('a network failure says the server is unreachable', async () => {
    loginAnswers(() => HttpResponse.error());
    await expect(signIn('a@b.c', 'x')).rejects.toThrow(
      'Can’t reach the server. Check your connection and try again.',
    );
  });

  it('a 401 is the unsupported second step (MFA)', async () => {
    loginAnswers(() => HttpResponse.json({ status: 401, data: { flows: [] } }, { status: 401 }));
    await expect(signIn('a@b.c', 'x')).rejects.toThrow('second sign-in step');
  });
});
