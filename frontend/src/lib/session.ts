/**
 * Cookies de session, partagés par proxy.ts et les routes /api/auth/*.
 *
 * Les jetons ne quittent jamais le serveur Next : httpOnly, le JavaScript
 * du navigateur ne peut pas les lire, donc un script injecté ne peut pas les
 * voler.
 */

export const ACCESS_COOKIE = 'session_access';
export const REFRESH_COOKIE = 'session_refresh';

const base = {
  httpOnly: true,
  // Cloudflare termine le TLS : en production la page est toujours en HTTPS.
  secure: process.env.NODE_ENV === 'production',
  sameSite: 'lax' as const,
  path: '/',
};

// Alignés sur SIMPLE_JWT (config/settings.py).
export const accessCookieOptions = { ...base, maxAge: 60 * 15 };
export const refreshCookieOptions = { ...base, maxAge: 60 * 60 * 24 * 7 };

export const DJANGO_API_URL = (process.env.DJANGO_API_URL || 'http://127.0.0.1:8000/api').replace(/\/$/, '');

/** Secondes avant expiration, lues sans vérifier la signature.
 *
 * Sert uniquement à décider s'il faut renouveler le jeton. Aucune
 * autorisation n'en dépend : Django vérifie la signature à chaque appel.
 */
export function secondsLeft(token: string | undefined): number {
  if (!token) return -1;
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp === 'number' ? payload.exp - Date.now() / 1000 : -1;
  } catch {
    return -1;
  }
}
