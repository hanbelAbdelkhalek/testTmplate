import { NextResponse } from 'next/server';
import { djangoFetch } from '@/lib/django';
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  accessCookieOptions,
  refreshCookieOptions,
} from '@/lib/session';

/** Connexion : Django vérifie, Next garde les jetons dans des cookies httpOnly. */
export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  if (!body || typeof body.username !== 'string' || typeof body.password !== 'string') {
    return NextResponse.json({ detail: 'Identifiant et mot de passe requis.' }, { status: 400 });
  }

  let response: Response;
  try {
    response = await djangoFetch('/auth/login/', {
      method: 'POST',
      body: { username: body.username, password: body.password },
      token: null,
    });
  } catch {
    return NextResponse.json({ detail: 'Service momentanément indisponible.' }, { status: 502 });
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    return NextResponse.json(data, { status: response.status });
  }

  // Les jetons ne sont pas renvoyés au navigateur : seulement les cookies.
  const result = NextResponse.json({ ok: true });
  result.cookies.set(ACCESS_COOKIE, data.access, accessCookieOptions);
  result.cookies.set(REFRESH_COOKIE, data.refresh, refreshCookieOptions);
  return result;
}
