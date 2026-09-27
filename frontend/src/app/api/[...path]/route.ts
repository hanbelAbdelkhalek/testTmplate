import { NextResponse } from 'next/server';
import { djangoFetch } from '@/lib/django';

/**
 * Relais du navigateur vers Django : /api/<chemin> → Django /api/<chemin>.
 *
 * Refusés ici, quoi que dise Django :
 *  - internal/ : l'API de la plateforme. Signée, donc déjà protégée, mais
 *    elle n'a rien à faire sur l'Internet public.
 *  - auth/refresh : le jeton de renouvellement reste dans son cookie
 *    httpOnly ; le renouvellement se fait dans proxy.ts.
 */
const BLOCKED = [/^internal(\/|$)/, /^auth\/refresh(\/|$)/, /^auth\/login(\/|$)/];

async function relay(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const joined = path.join('/');
  if (BLOCKED.some((pattern) => pattern.test(joined)) || path.some((p) => p === '..')) {
    return NextResponse.json({ detail: 'Introuvable.' }, { status: 404 });
  }

  const url = new URL(request.url);
  const hasBody = !['GET', 'HEAD'].includes(request.method);
  let response: Response;
  try {
    response = await djangoFetch(`/${joined}/${url.search}`, {
      method: request.method,
      rawBody: hasBody ? await request.text() : undefined,
    });
  } catch {
    return NextResponse.json({ detail: 'Service momentanément indisponible.' }, { status: 502 });
  }

  if (response.status >= 300 && response.status < 400) {
    console.error(`Django a redirigé ${request.method} /api/${joined} vers ${response.headers.get('location')}`);
    return NextResponse.json({ detail: 'Réponse inattendue du serveur.' }, { status: 502 });
  }
  return new NextResponse(response.status === 204 ? null : await response.text(), {
    status: response.status,
    headers: { 'Content-Type': response.headers.get('content-type') ?? 'application/json' },
  });
}

export { relay as GET, relay as POST, relay as PUT, relay as PATCH, relay as DELETE };
