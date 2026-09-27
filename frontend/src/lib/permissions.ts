import type { Me } from './types';

/**
 * Pour l'AFFICHAGE seulement : cacher ce que le compte ne peut pas faire.
 * Django refuse de toute façon — un bouton caché n'est pas une protection.
 */
export function can(me: Me, permission: string): boolean {
  return me.permissions.includes(permission);
}

export function moduleEnabled(me: Me, key: string): boolean {
  return me.entitlements.modules.some((m) => m.key === key && m.enabled);
}
