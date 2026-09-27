'use client';

import { FormEvent, Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';

function LoginForm() {
  const params = useSearchParams();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (response.ok) {
      // Seulement un chemin local : un paramètre `next` pointant ailleurs
      // ferait de cette page un tremplin vers un faux site.
      const next = params.get('next') ?? '';
      window.location.href = next.startsWith('/') && !next.startsWith('//') ? next : '/dashboard';
      return;
    }
    const data = await response.json().catch(() => ({}));
    setError(
      response.status === 404
        ? 'Aucun espace à cette adresse.'
        : data.detail ?? 'Connexion impossible.',
    );
    setBusy(false);
  };

  return (
    <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
      <h1 className="text-lg font-bold">Connexion</h1>
      <label className="block space-y-1 text-sm font-medium">
        Identifiant
        <input className="field" value={username} onChange={(e) => setUsername(e.target.value)}
          autoComplete="username" autoFocus required />
      </label>
      <label className="block space-y-1 text-sm font-medium">
        Mot de passe
        <input className="field" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password" required />
      </label>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <button className="btn w-full" disabled={busy}>{busy ? 'Connexion…' : 'Se connecter'}</button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
