/** Ce que renvoie GET /api/auth/me/ — de quoi construire le menu. */
export interface Me {
  account: Account;
  permissions: string[];
  tenant: { slug: string; name: string; is_demo: boolean };
  entitlements: {
    revision: number;
    plan_key: string;
    modules: { key: string; label: string; enabled: boolean; limits: Record<string, number | null> }[];
    usage: Record<string, number>;
  };
}

export interface Account {
  id: number;
  username: string;
  name: string;
  email: string;
  role: string;
  role_label: string;
  status: 'active' | 'inactive';
  last_login: string | null;
  created_at: string;
}

export interface Role {
  key: string;
  label: string;
}

export interface Item {
  id: number;
  sku: string;
  name: string;
  price: string;
  is_active: boolean;
}

/** Erreur renvoyée par l'API : `code` pour décider, `detail` pour afficher. */
export interface ApiError {
  detail?: string;
  code?: string;
  [field: string]: unknown;
}
