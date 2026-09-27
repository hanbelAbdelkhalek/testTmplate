from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.core import solution

from .models import TenantModule


class LimitReached(PermissionDenied):
    default_detail = "La limite de votre abonnement est atteinte."
    default_code = "limit_reached"


class StaleRevision(Exception):
    """La plateforme a envoyé une révision plus ancienne que celle appliquée."""


class UnknownModule(ValueError):
    pass


def is_module_enabled(tenant, key: str) -> bool:
    """Le module est-il ouvert pour cet espace ?

    Une clé qui n'est pas un module vendable (hors solution.MODULES) est
    toujours ouverte : c'est le socle. Un module sans ligne prend sa valeur
    par défaut — jamais « ouvert » d'office, sans quoi un espace neuf aurait
    tout ce qu'il n'a pas acheté.
    """
    if key not in solution.MODULES:
        return True
    if tenant is None:
        return False
    row = TenantModule.objects.filter(tenant=tenant, key=key).only("enabled").first()
    if row is None:
        return bool(solution.MODULES[key].get("default_enabled", False))
    return row.enabled


def get_limit(tenant, module: str, name: str):
    """Le plafond `name` du module pour cet espace, ou None si illimité."""
    default = solution.MODULES.get(module, {}).get("limits", {}).get(name)
    row = TenantModule.objects.filter(tenant=tenant, key=module).only("limits").first()
    if row is not None and name in (row.limits or {}):
        return row.limits[name]
    return default


def check_limit(tenant, module: str, name: str, used: int) -> None:
    """Lève LimitReached si ajouter un élément dépasserait le plafond.

    À appeler AVANT de créer. Un plafond abaissé sous l'existant bloque les
    ajouts sans rien supprimer : les lignes déjà là portent des données.
    """
    limit = get_limit(tenant, module, name)
    if limit is not None and used >= int(limit):
        raise LimitReached(
            f"Limite atteinte : {limit} au maximum pour cet abonnement ({module}.{name})."
        )


def ensure_default_modules(tenant) -> None:
    """Pose une ligne par module manquant, à sa valeur par défaut."""
    for key, spec in solution.MODULES.items():
        TenantModule.objects.get_or_create(
            tenant=tenant, key=key, defaults={"enabled": bool(spec.get("default_enabled"))}
        )


@transaction.atomic
def apply_entitlements(tenant, *, revision: int, modules: list, limits: dict, plan_key: str = ""):
    """Applique ce que la plateforme a vendu. Renvoie True si appliqué, False si déjà à jour.

    `modules` : [{"key": "catalog", "enabled": true}, …] — un module absent de
    la liste garde son état. `limits` : {"catalog": {"max_items": 500}}.

    Une révision plus ancienne lève StaleRevision : deux mises à jour arrivées
    dans le désordre ne doivent pas rouvrir ce qu'on vient de fermer. La même
    révision renvoyée est acceptée sans rien changer (nouvel essai réseau).
    """
    tenant = type(tenant).objects.select_for_update().get(pk=tenant.pk)
    if revision < tenant.entitlement_revision:
        raise StaleRevision(
            f"Révision {revision} plus ancienne que la révision appliquée "
            f"{tenant.entitlement_revision}."
        )
    if revision == tenant.entitlement_revision and tenant.entitlement_revision > 0:
        return False

    inconnus = sorted(
        {m["key"] for m in modules} - set(solution.MODULES)
        | set(limits or {}) - set(solution.MODULES)
    )
    if inconnus:
        # Enregistrée, une clé inconnue ne fermerait rien, et l'erreur ne se
        # verrait qu'au moment où le client utiliserait encore le module.
        raise UnknownModule(f"Modules inconnus de cette solution : {', '.join(inconnus)}.")

    ensure_default_modules(tenant)
    for item in modules:
        TenantModule.objects.filter(tenant=tenant, key=item["key"]).update(
            enabled=bool(item["enabled"])
        )
    for key, values in (limits or {}).items():
        row = TenantModule.objects.get(tenant=tenant, key=key)
        row.limits = {**(row.limits or {}), **(values or {})}
        row.save(update_fields=["limits", "updated_at"])

    tenant.entitlement_revision = revision
    if plan_key:
        tenant.plan_key = plan_key
    tenant.save(update_fields=["entitlement_revision", "plan_key", "updated_at"])
    return True


def entitlement_state(tenant) -> dict:
    """Ce que l'espace a le droit d'utiliser, et ce qu'il utilise déjà."""
    rows = {row.key: row for row in TenantModule.objects.filter(tenant=tenant)}
    modules = []
    for key, spec in solution.MODULES.items():
        row = rows.get(key)
        limits = {**spec.get("limits", {}), **((row.limits or {}) if row else {})}
        modules.append(
            {
                "key": key,
                "label": spec["label"],
                "enabled": row.enabled if row else bool(spec.get("default_enabled")),
                "limits": limits,
            }
        )
    return {
        "revision": tenant.entitlement_revision,
        "plan_key": tenant.plan_key,
        "modules": modules,
        "usage": usage(tenant),
    }


def usage(tenant) -> dict:
    """Consommation actuelle, pour que la plateforme voie qu'un plafond de 2 est
    en dessous des 5 éléments déjà créés. À compléter par module."""
    from apps.catalog.models import Item
    from apps.identity.models import Account

    return {
        "accounts": Account.objects.filter(tenant=tenant).count(),
        "catalog.items": Item.objects.for_tenant(tenant).count(),
    }
