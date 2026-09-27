import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import {
  ACCESS_COOKIE,
  DJANGO_API_URL,
  REFRESH_COOKIE,
  accessCookieOptions,
  secondsLeft,
} from '@/lib/session';

/**
 * Avant chaque page du tableau de bord et chaque appel /api :
 *  1. renouvelle le jeton d'accès s'il expire (15 min), avec le jeton de
 *     renouvellement — sinon une session ouverte retomberait sur la page de
 *     connexion toutes les quinze minutes ;
 *  2. envoie vers /login une page du tableau de bord sans session.
 *
 * Un aiguillage, pas une autorisation : Django vérifie tout, à chaque appel.
 */
export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const isPage = pathname.startsWith('/dashboard');
  const isLogin = pathname === '/login';

  let access = request.cookies.get(ACCESS_COOKIE)?.value;
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  let renewed: string | null = null;

  if (secondsLeft(access) < 30 && refresh) {
    renewed = await renew(refresh, request.headers.get('host') ?? '');
    access = renewed ?? undefined;
  }
  const signedIn = secondsLeft(access) > 0;

  if (isLogin) {
    return signedIn ? withCookie(NextResponse.redirect(new URL('/dashboard', request.url)), renewed) : NextResponse.next();
  }
  if (isPage && !signedIn) {
    const login = new URL('/login', request.url);
    login.searchParams.set('next', pathname + search);
    const response = NextResponse.redirect(login);
    response.cookies.delete(ACCESS_COOKIE);
    response.cookies.delete(REFRESH_COOKIE);
    return response;
  }

  if (renewed) {
    // Le nouveau jeton doit servir dès cette requête : on le pose aussi sur
    // la requête transmise, pas seulement sur la réponse.
    request.cookies.set(ACCESS_COOKIE, renewed);
    return withCookie(NextResponse.next({ request: { headers: request.headers } }), renewed);
  }
  return NextResponse.next();
}

async function renew(refresh: string, host: string): Promise<string | null> {
  try {
    const response = await fetch(`${DJANGO_API_URL}/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Forwarded-Host': host },
      body: JSON.stringify({ refresh }),
      cache: 'no-store',
    });
    if (!response.ok) return null;
    const data = await response.json();
    return typeof data.access === 'string' ? data.access : null;
  } catch {
    return null;
  }
}

function withCookie(response: NextResponse, token: string | null): NextResponse {
  if (token) response.cookies.set(ACCESS_COOKIE, token, accessCookieOptions);
  return response;
}

export const config = {
  // Ni la connexion ni la déconnexion, qui posent elles-mêmes leurs
  // cookies ; ni les fichiers statiques.
  matcher: ['/dashboard/:path*', '/login', '/api/((?!auth/login|auth/logout).*)'],
};
