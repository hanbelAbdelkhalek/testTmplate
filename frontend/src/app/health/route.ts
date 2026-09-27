// Sondé par Docker et par la plateforme : le serveur Next répond.
export const dynamic = 'force-dynamic';

export function GET() {
  return new Response('ok', { headers: { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' } });
}
