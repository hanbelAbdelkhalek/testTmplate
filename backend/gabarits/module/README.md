# Module {{ app_name }}

Créé par `scripts/nouveau-module.sh {{ app_name }}`.

Pour le brancher, quatre ajouts :

1. `config/settings.py` → `INSTALLED_APPS` : `"apps.{{ app_name }}"`.
2. `apps/core/solution.py` → `MODULES["{{ app_name }}"]` et les permissions
   `{{ app_name }}.view` / `{{ app_name }}.manage` dans `MODULE_PERMISSIONS`,
   puis les donner aux rôles voulus dans `ROLES`.
3. `config/urls.py` → `router.register("{{ app_name }}/elements", ElementViewSet, basename="{{ app_name }}-element")`.
4. `solution.yaml` → le module dans `spec.modules`.

Puis : `python manage.py makemigrations {{ app_name }}` et `python manage.py test`.
