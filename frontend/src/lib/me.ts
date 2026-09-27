import 'server-only';
import { cache } from 'react';
import { djangoFetch } from './django';
import type { Me } from './types';

export type MeResult =
  | { kind: 'ok'; me: Me }
  | { kind: 'signed_out' }
  | { kind: 'no_tenant' }
  | { kind: 'suspended' }
  | { kind: 'unavailable' };

/** Le compte connecté, lu une fois par rendu (mis en cache par React). */
export const getMe = cache(async (): Promise<MeResult> => {
  let response: Response;
  try {
    response = await djangoFetch('/auth/me/');
  } catch {
    return { kind: 'unavailable' };
  }
  if (response.ok) return { kind: 'ok', me: (await response.json()) as Me };
  if (response.status === 401) return { kind: 'signed_out' };
  const data = await response.json().catch(() => ({}));
  if (data.code === 'tenant_not_found') return { kind: 'no_tenant' };
  if (data.code === 'tenant_suspended') return { kind: 'suspended' };
  if (response.status === 403) return { kind: 'signed_out' };
  return { kind: 'unavailable' };
});
