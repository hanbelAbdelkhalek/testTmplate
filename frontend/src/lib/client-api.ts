'use client';

import type { ApiError } from './types';

/**
 * Appel depuis le navigateur. Passe par /api/… du serveur Next, qui ajoute
 * le jeton et l'espace ; le navigateur ne parle jamais à Django.
 *
 * Chemins SANS barre finale (`/catalog/items`, pas `/catalog/items/`) : Next
 * redirigerait chaque appel. Le relais la rajoute pour Django.
 */
export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<{ ok: true; data: T } | { ok: false; status: number; error: ApiError }> {
  const response = await fetch(`/api${path}`, {
    method: init.method ?? 'GET',
    headers: init.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (response.status === 401) {
    // Session finie : retour à la connexion, en revenant ici ensuite.
    // Rechargement complet voulu : il efface l'état de la page précédente.
    window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) return { ok: false, status: response.status, error: (data ?? {}) as ApiError };
  return { ok: true, data: data as T };
}

/** Le message à montrer, y compris les erreurs de validation par champ de DRF. */
export function errorText(error: ApiError, fallback = 'Une erreur est survenue.'): string {
  if (typeof error.detail === 'string') return error.detail;
  const messages = Object.values(error)
    .flat()
    .filter((v): v is string => typeof v === 'string');
  return messages.length ? messages.join(' ') : fallback;
}
