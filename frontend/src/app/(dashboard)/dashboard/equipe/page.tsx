'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { api, errorText } from '@/lib/client-api';
import type { Account, Role } from '@/lib/types';

const EMPTY = { name: '', username: '', email: '', password: '', role: '' };

const fetchTeam = () => api<{ accounts: Account[]; roles: Role[] }>('/accounts');

/**
 * Les comptes de l'espace, gérés par le client lui-même.
 * La plateforme peut faire la même chose de son côté (API interne) : les
 * deux passent par les mêmes règles (backend/apps/identity/services.py).
 */
export default function TeamPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [passwordFor, setPasswordFor] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const apply = useCallback((result: Awaited<ReturnType<typeof fetchTeam>>) => {
    if (result.ok) {
      setAccounts(result.data.accounts);
      setRoles(result.data.roles);
    } else {
      setError(errorText(result.error, 'Impossible de charger les comptes.'));
    }
  }, []);
  const load = useCallback(async () => apply(await fetchTeam()), [apply]);

  useEffect(() => {
    let alive = true;
    fetchTeam().then((result) => alive && apply(result));
    return () => {
      alive = false;
    };
  }, [apply]);

  const run = async (action: () => ReturnType<typeof api>, success: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await action();
    if (result.ok) {
      setNotice(success);
      await load();
    } else {
      setError(errorText(result.error));
    }
    setBusy(false);
    return result.ok;
  };

  const create = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await run(
      () => api('/accounts', { method: 'POST', body: { ...form, role: form.role || undefined } }),
      `Compte ${form.username} créé.`,
    );
    if (ok) setForm(EMPTY);
  };

  const patch = (account: Account, body: Record<string, string>, success: string) =>
    run(() => api(`/accounts/${account.id}`, { method: 'PATCH', body }), success);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Équipe</h1>
      {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {notice && <p role="status" className="rounded-lg bg-green-50 p-3 text-sm text-green-700">{notice}</p>}

      <section className="card overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="py-2">Nom</th><th>Identifiant</th><th>Rôle</th><th>État</th><th />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {accounts.map((account) => (
              <tr key={account.id}>
                <td className="py-2">
                  <p className="font-medium">{account.name}</p>
                  <p className="text-xs text-slate-500">{account.email}</p>
                </td>
                <td className="font-mono text-xs">{account.username}</td>
                <td>
                  <select
                    className="field w-auto py-1"
                    value={account.role}
                    disabled={busy}
                    onChange={(e) => patch(account, { role: e.target.value }, 'Rôle modifié.')}
                  >
                    {roles.map((role) => <option key={role.key} value={role.key}>{role.label}</option>)}
                  </select>
                </td>
                <td>
                  <button
                    className="btn-ghost"
                    disabled={busy}
                    onClick={() =>
                      patch(
                        account,
                        { status: account.status === 'active' ? 'inactive' : 'active' },
                        account.status === 'active' ? 'Compte désactivé.' : 'Compte réactivé.',
                      )
                    }
                  >
                    {account.status === 'active' ? 'Actif' : 'Désactivé'}
                  </button>
                </td>
                <td className="text-right">
                  {passwordFor === account.id ? (
                    <form
                      className="flex justify-end gap-1"
                      onSubmit={async (e) => {
                        e.preventDefault();
                        if (await patch(account, { password: newPassword }, 'Mot de passe remplacé.')) {
                          setPasswordFor(null);
                          setNewPassword('');
                        }
                      }}
                    >
                      <input className="field w-40 py-1" type="password" autoComplete="new-password"
                        value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="Nouveau mot de passe" required />
                      <button className="btn-ghost" disabled={busy}>OK</button>
                    </form>
                  ) : (
                    <button className="btn-ghost" onClick={() => setPasswordFor(account.id)}>
                      Mot de passe
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <form onSubmit={create} className="card grid gap-3 md:grid-cols-2">
        <h2 className="font-semibold md:col-span-2">Ajouter un compte</h2>
        <input className="field" placeholder="Nom" value={form.name} required
          onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className="field" placeholder="Identifiant" value={form.username} required
          onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input className="field" type="email" placeholder="E-mail" value={form.email} required
          onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <input className="field" type="password" placeholder="Mot de passe" autoComplete="new-password"
          value={form.password} required onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <select className="field" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          <option value="">Rôle par défaut</option>
          {roles.map((role) => <option key={role.key} value={role.key}>{role.label}</option>)}
        </select>
        <button className="btn" disabled={busy}>Créer le compte</button>
      </form>
    </div>
  );
}
