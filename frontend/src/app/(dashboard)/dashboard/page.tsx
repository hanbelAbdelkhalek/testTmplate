import { getMe } from '@/lib/me';

export default async function Overview() {
  const result = await getMe();
  if (result.kind !== 'ok') return null; // le layout affiche déjà la raison
  const { me } = result;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Bonjour {me.account.name}</h1>

      <section className="card">
        <h2 className="font-semibold">Votre abonnement</h2>
        <ul className="mt-3 divide-y divide-slate-100 text-sm">
          {me.entitlements.modules.map((module) => (
            <li key={module.key} className="flex items-center justify-between py-2">
              <span>{module.label}</span>
              <span className={module.enabled ? 'text-green-700' : 'text-slate-400'}>
                {module.enabled ? 'Inclus' : 'Non inclus'}
                {Object.entries(module.limits)
                  .filter(([, value]) => value !== null)
                  .map(([name, value]) => ` · ${name} : ${value}`)}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2 className="font-semibold">Vos droits</h2>
        <p className="mt-2 text-sm text-slate-600">
          Rôle : {me.account.role_label} — {me.permissions.length} permission(s).
        </p>
      </section>
    </div>
  );
}
