# Module {{ app_name }}

Créé par `scripts/nouveau-module.sh {{ app_name }}`.

Pour le brancher, quatre ajouts :

1. `config/settings.py` → `INSTALLED_APPS` : `"apps.{{ app_name }}"`.
2. `apps/core/solution.py` → `MODULES["{{ app_name }}"]` et les permissions
   `{{ app_name }}.view` / `{{ app_name }}.manage` dans `MODULE_PERMISSIONS`,
   puis les donner aux rôles voulus dans `ROLES`.
3. `config/urls.py` → `from apps.{{ app_name }}.views import ElementViewSet`, puis
   `router.register("{{ app_name }}/elements", ElementViewSet, basename="{{ app_name }}-element")`.
4. `solution.yaml` → le module dans `spec.modules` (même clé, même libellé).

Puis : `python manage.py makemigrations {{ app_name }}` et `python manage.py test`
(le `tests.py` du module vérifie déjà que deux espaces ne se voient pas).

Côté frontend : copier `frontend/src/app/(dashboard)/dashboard/catalogue/` en
`{{ app_name }}/`, remplacer `/catalog/items` par `/{{ app_name }}/elements`, et
ajouter l'entrée du menu dans `frontend/src/app/(dashboard)/dashboard/layout.tsx`
(`moduleEnabled(me, '{{ app_name }}') && can(me, '{{ app_name }}.view')`).
