'use client';

/**
 * MODULE D'EXEMPLE — la page d'un module métier : lire, créer, supprimer,
 * et réagir quand le module est fermé ou la limite atteinte.
 */

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { api, errorText } from '@/lib/client-api';
import type { Item } from '@/lib/types';

const fetchItems = () => api<{ results: Item[] }>('/catalog/items');

export default function CataloguePage() {
  const [items, setItems] = useState<Item[]>([]);
  const [closed, setClosed] = useState(false);
  const [form, setForm] = useState({ sku: '', name: '', price: '' });
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((result: Awaited<ReturnType<typeof fetchItems>>) => {
    if (result.ok) setItems(result.data.results);
    // Le serveur a le dernier mot : le menu peut être en retard sur un
    // module que la plateforme vient de fermer.
    else if (result.error.code === 'module_closed') setClosed(true);
    else setError(errorText(result.error));
  }, []);
  const load = useCallback(async () => apply(await fetchItems()), [apply]);

  useEffect(() => {
    let alive = true;
    fetchItems().then((result) => alive && apply(result));
    return () => {
      alive = false;
    };
  }, [apply]);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const result = await api('/catalog/items', { method: 'POST', body: { ...form, price: form.price || '0' } });
    if (result.ok) {
      setForm({ sku: '', name: '', price: '' });
      await load();
    } else {
      setError(errorText(result.error));
    }
  };

  const remove = async (item: Item) => {
    const result = await api(`/catalog/items/${item.id}`, { method: 'DELETE' });
    if (result.ok) await load();
    else setError(errorText(result.error));
  };

  if (closed) {
    return <p className="card">Le catalogue n&apos;est pas inclus dans votre abonnement.</p>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Catalogue</h1>
      {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <section className="card">
        {items.length === 0 ? (
          <p className="text-sm text-slate-500">Aucun article.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {items.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 py-2">
                <span><span className="font-mono text-xs text-slate-500">{item.sku}</span> {item.name}</span>
                <span className="flex items-center gap-3">
                  {item.price} MAD
                  <button className="btn-ghost" onClick={() => remove(item)}>Supprimer</button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <form onSubmit={create} className="card grid gap-3 md:grid-cols-4">
        <input className="field" placeholder="Référence" value={form.sku} required
          onChange={(e) => setForm({ ...form, sku: e.target.value })} />
        <input className="field md:col-span-2" placeholder="Nom" value={form.name} required
          onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className="field" placeholder="Prix" inputMode="decimal" value={form.price}
          onChange={(e) => setForm({ ...form, price: e.target.value })} />
        <button className="btn md:col-span-4">Ajouter</button>
      </form>
    </div>
  );
}
