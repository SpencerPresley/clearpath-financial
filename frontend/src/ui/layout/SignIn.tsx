/*
 * Sign-in for the demo's email/password accounts (allauth headless). Deliberately minimal: no reset, signup
 * (accounts are provisioned by an admin), or MFA step. The seeded demo accounts are listed so an evaluator can
 * pick a role; their password is handed out with the demo, not shown here.
 */
import { useState } from 'react';
import type { SyntheticEvent } from 'react';
import { Input, Label, TextField } from 'react-aria-components';

import { Button } from '../Button';
import { signIn } from './session';

export const DEMO_ACCOUNTS: readonly { email: string; role: string }[] = [
  { email: 'reviewer@clearpath.demo', role: 'Reviewer' },
  { email: 'lead@clearpath.demo', role: 'Compliance lead' },
  { email: 'marketer@clearpath.demo', role: 'Marketer' },
  { email: 'admin@clearpath.demo', role: 'Admin' },
];

export function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    setPending(true);
    setProblem(null);
    signIn(email.trim(), password).then(
      () => {
        setPending(false);
        onSignedIn();
      },
      (error: unknown) => {
        setPending(false);
        setProblem(error instanceof Error ? error.message : 'Couldn’t sign in. Try again.');
      },
    );
  };

  return (
    <div className="app-signin">
      <header className="app-topbar">
        <span className="app-wordmark pl-2">
          <span className="app-wordmark-mark" aria-hidden="true" />
          <span>ClearPath</span>
          <span className="app-wordmark-product">Compliance Review</span>
        </span>
      </header>
      <main className="app-signin-main">
        <form className="app-signin-form" onSubmit={submit} aria-labelledby="signin-title">
          <h1 id="signin-title" className="app-page-title">
            Sign in
          </h1>
          <TextField
            value={email}
            onChange={setEmail}
            type="email"
            autoComplete="username"
            isRequired
            autoFocus
          >
            <Label className="app-field-label">Email</Label>
            <Input className="app-input" />
          </TextField>
          <TextField
            value={password}
            onChange={setPassword}
            type="password"
            autoComplete="current-password"
            isRequired
          >
            <Label className="app-field-label">Password</Label>
            <Input className="app-input" />
          </TextField>
          {problem !== null && (
            <p role="alert" className="app-field-error">
              {problem}
            </p>
          )}
          <Button
            type="submit"
            variant="primary"
            isDisabled={pending || email.trim() === '' || password === ''}
          >
            {pending ? 'Signing in…' : 'Sign in'}
          </Button>
          <div className="app-signin-demo">
            <p className="text-meta font-medium text-muted">Demo accounts</p>
            <ul className="flex flex-col gap-0.5">
              {DEMO_ACCOUNTS.map((account) => (
                <li key={account.email}>
                  <button
                    type="button"
                    className="app-signin-demo-btn"
                    onClick={() => {
                      setEmail(account.email);
                    }}
                  >
                    <span className="font-mono text-meta">{account.email}</span>
                    <span className="text-meta text-muted">{account.role}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </form>
      </main>
    </div>
  );
}
