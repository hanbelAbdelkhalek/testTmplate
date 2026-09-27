import Link from 'next/link';
import { redirect } from 'next/navigation';
import { LogoutButton } from '@/components/LogoutButton';
import { getMe } from '@/lib/me';
import { can, moduleEnabled } from '@/lib/permissions';
import type { Me } from '@/lib/types';

/**
 * Le menu. Une entrée par module, affichée si le module est ouvert ET si le
 * compte a la permission. Ajouter ici chaque nouveau module.
 */
function navigation(me: Me) {
  return [
    { href: '/dashboard', label: 'Accueil', show: true },
    { href: '/dashboard/catalogue', label: 'Catalogue', show: moduleEnabled(me, 'catalog') && can(me, 'catalog.view') },
    { href: '/dashboard/equipe', label: 'Équipe', show: can(me, 'accounts.view') },
  ].filter((item) => item.show);
}

export default async function DashboardLayout({ children }: LayoutProps<'/dashboard'>) {
  const result = await getMe();
  if (result.kind === 'signed_out') redirect('/login');
  if (result.kind !== 'ok') {
    const message = {
      no_tenant: 'Aucun espace à cette adresse.',
      suspended: 'Cet espace est suspendu. Contactez SigmaGravity.',
      unavailable: 'Service momentanément indisponible. Réessayez dans un instant.',
    }[result.kind];
    return <main className="flex min-h-screen items-center justify-center p-4"><p className="card">{message}</p></main>;
  }

  const { me } = result;
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-slate-200 bg-white p-4 md:w-60 md:border-b-0 md:border-r">
        <p className="font-bold">{me.tenant.name}</p>
        {me.tenant.is_demo && (
          <p className="mt-1 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
            Démonstration
          </p>
        )}
        <nav className="mt-4 flex gap-1 overflow-x-auto md:flex-col">
          {navigation(me).map((item) => (
            <Link key={item.href} href={item.href} className="rounded-lg px-3 py-2 text-sm font-medium hover:bg-slate-100">
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="mt-6 border-t border-slate-200 pt-4 text-sm">
          <p className="font-medium">{me.account.name}</p>
          <p className="text-slate-500">{me.account.role_label}</p>
          <LogoutButton />
        </div>
      </aside>
      <main className="flex-1 p-4 md:p-8">{children}</main>
    </div>
  );
}
