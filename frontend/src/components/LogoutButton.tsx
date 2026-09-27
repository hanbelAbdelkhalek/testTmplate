'use client';

import { useRouter } from 'next/navigation';

export function LogoutButton() {
  const router = useRouter();
  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.replace('/login');
    router.refresh();
  };
  return (
    <button type="button" onClick={logout} className="btn-ghost mt-3 w-full">
      Se déconnecter
    </button>
  );
}
