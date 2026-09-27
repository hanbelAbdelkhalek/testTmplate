import 'server-only';
import { cookies, headers } from 'next/headers';
import { ACCESS_COOKIE, DJANGO_API_URL } from './session';

/**
 * Appel à Django depuis le serveur Next (composants serveur, routes /api).
 *
 * Django n'est joint que d'ici, sur le réseau Docker. Deux en-têtes font
 * le lien avec le navigateur :
 *  - X-Forwarded-Host : l'adresse que le client a tapée. C'est elle qui
 *    désigne l'espace. Posée ici à partir de l'en-tête Host reçu, jamais
 *    recopiée d'un X-Forwarded-Host envoyé par le navigateur — sinon
 *    n'importe qui choisirait son espace.
 *  - Authorization : le jeton du cookie httpOnly.
 */
export async function djangoFetch(
  path: string,
  init: { method?: string; body?: unknown; rawBody?: string; token?: string | null; host?: string } = {},
): Promise<Response> {
  const h = new Headers({ Accept: 'application/json' });
  h.set('X-Forwarded-Host', init.host ?? (await currentHost()));

  const token = init.token === undefined ? (await cookies()).get(ACCESS_COOKIE)?.value : init.token;
  if (token) h.set('Authorization', `Bearer ${token}`);

  let body: string | undefined;
  if (init.rawBody !== undefined) body = init.rawBody;
  else if (init.body !== undefined) body = JSON.stringify(init.body);
  if (body !== undefined) h.set('Content-Type', 'application/json');

  return fetch(`${DJANGO_API_URL}${path}`, {
    method: init.method ?? 'GET',
    headers: h,
    body,
    cache: 'no-store',
    // Une redirection de Django est une panne de configuration (HTTPS forcé,
    // barre oblique manquante) : la suivre en silence masquerait l'erreur.
    redirect: 'manual',
  });
}

export async function currentHost(): Promise<string> {
  return (await headers()).get('host') ?? '';
}
