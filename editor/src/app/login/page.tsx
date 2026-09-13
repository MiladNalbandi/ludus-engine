'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { signIn } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
      router.push('/');
    } catch {
      // Deliberately the same message whatever went wrong. The engine answers every
      // authentication failure identically so that a login form cannot be used to find out who
      // has an account, and a more helpful message here would undo that.
      setError('Those credentials were not accepted.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: '24rem', margin: '12vh auto', padding: '0 1rem' }}>
      <h1 style={{ marginBottom: '0.25rem' }}>Ludus</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Sign in to the engine this editor is pointed at.
      </p>
      <form className="panel" onSubmit={submit}>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <label htmlFor="password" style={{ marginTop: '1rem' }}>
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {error ? (
          <p className="error" role="alert" style={{ marginBottom: 0 }}>
            {error}
          </p>
        ) : null}
        <button type="submit" disabled={busy} style={{ marginTop: '1.25rem', width: '100%' }}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  );
}
