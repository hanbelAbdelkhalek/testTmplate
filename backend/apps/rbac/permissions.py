from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from apps.core import solution
from apps.entitlements.services import is_module_enabled


class ModuleClosed(PermissionDenied):
    default_detail = "Ce module n'est pas inclus dans l'abonnement de cet espace."
    default_code = "module_closed"


class SolutionPermission(BasePermission):
    """Permission par défaut de toute vue.

    Ordre d'évaluation (les deux premières étapes sont dans le middleware) :
      1. espace résolu depuis l'hôte          apps.tenancy.middleware
      2. espace actif                          apps.tenancy.middleware
      3. compte de CET espace, actif           apps.identity.authentication
      4. module ouvert                          ici — refusé même à un admin
      5. permission du rôle                     ici
      6. limite                                 dans la vue, à la création
      7. portée de l'espace                     TenantScopedViewSet
    Cacher un bouton dans le frontend n'est jamais une autorisation.

    Une vue déclare :
        module = "catalog"
        permissions = {"list": "catalog.view", "*": "catalog.manage"}
    ou `permission = "accounts.view"` pour une APIView simple.
    Une vue publique met `permission_classes = [AllowAny]` explicitement.
    """

    def has_permission(self, request, view):
        account = getattr(request.user, "account", None) if request.user else None
        if account is None or not account.is_active:
            return False

        module = getattr(view, "module", None)
        if module and not is_module_enabled(request.tenant, module):
            raise ModuleClosed()

        required = required_permission(request, view)
        if required is DENY:
            return False
        if required is None:
            return True
        # Un module fermé coupe aussi ses permissions quand la vue ne l'a pas
        # déclaré : la permission porte le nom de son module.
        prefix = required.split(".", 1)[0]
        if prefix in solution.MODULES and not is_module_enabled(request.tenant, prefix):
            raise ModuleClosed()
        return account.has_permission(required)


# Une action absente d'une table de permissions est refusée : oublier une
# action en ajoutant une route ne doit pas l'ouvrir à tous les comptes.
DENY = object()


def required_permission(request, view):
    table = getattr(view, "permissions", None)
    if table is not None:
        action = getattr(view, "action", None) or request.method.lower()
        return table.get(action, table.get("*", DENY))
    return getattr(view, "permission", None)
