"""
Espace de démonstration : une référence de données, et le retour à cette
référence.

L'administrateur de la plateforme remplit la démo à la main, puis enregistre
son état (`capturer`). Chaque nuit, la plateforme demande le retour à cet état
(`restaurer`) : ce qu'un visiteur a ajouté, modifié ou supprimé disparaît.

Tout ce qui appartient à l'espace est pris : comptes (avec leur mot de passe),
rôles, modules, et toutes les tables métier (`TenantModel`). Jamais les données
d'un autre espace, jamais un espace qui n'est pas marqué démo.
"""

import json

from django.contrib.auth import get_user_model
from django.core import serializers
from django.core.serializers import sort_dependencies
from django.db import transaction

from apps.identity.models import Account

from .models import DemoSnapshot
from .services import tenant_models


class DemoError(Exception):
    def __init__(self, message: str, status: int = 409, code: str = "invalid"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def _verifier(tenant) -> None:
    if not tenant.is_demo:
        # Garde-fou absolu : restaurer efface les données de l'espace.
        raise DemoError("Cet espace n'est pas un espace de démonstration.", 409, "not_demo")


def _modeles_ordonnes():
    """Les tables de l'espace, dans un ordre où les clés étrangères se résolvent."""
    modeles = tenant_models()
    ordre = sort_dependencies([(m._meta.app_config, [m]) for m in modeles])
    return [m for m in ordre if m in modeles]


def compter(tenant) -> dict:
    return {
        m._meta.label: m._base_manager.filter(tenant=tenant).count()
        for m in _modeles_ordonnes()
        if m._base_manager.filter(tenant=tenant).exists()
    }


def capturer(tenant) -> DemoSnapshot:
    """Enregistre l'état actuel de l'espace comme référence."""
    _verifier(tenant)
    User = get_user_model()
    comptes = Account.objects.filter(tenant=tenant).values_list("user_id", flat=True)
    objets = list(User.objects.filter(pk__in=list(comptes)))
    for modele in _modeles_ordonnes():
        objets.extend(modele._base_manager.filter(tenant=tenant).order_by("pk"))
    donnees = json.loads(serializers.serialize("json", objets))
    snapshot, _ = DemoSnapshot.objects.update_or_create(tenant=tenant, defaults={"data": donnees})
    return snapshot


@transaction.atomic
def restaurer(tenant) -> dict:
    """Remet l'espace exactement dans l'état de sa référence."""
    _verifier(tenant)
    snapshot = DemoSnapshot.objects.filter(tenant=tenant).first()
    if snapshot is None:
        raise DemoError("Aucune référence enregistrée pour cette démo.", 409, "no_snapshot")

    # Effacer d'abord ce qui existe : comptes (et leurs utilisateurs), puis
    # les tables dans l'ordre inverse des dépendances.
    User = get_user_model()
    utilisateurs = list(Account.objects.filter(tenant=tenant).values_list("user_id", flat=True))
    Account.objects.filter(tenant=tenant).delete()
    User.objects.filter(pk__in=utilisateurs).delete()
    for modele in reversed(_modeles_ordonnes()):
        modele._base_manager.filter(tenant=tenant).delete()

    restaures = 0
    for objet in serializers.deserialize("json", json.dumps(snapshot.data)):
        # Ne jamais écrire dans un autre espace, même si la référence le disait.
        instance = objet.object
        if hasattr(instance, "tenant_id") and instance.tenant_id != tenant.pk:
            continue
        objet.save()
        restaures += 1
    return {"restored": restaures, "snapshot_at": snapshot.updated_at.isoformat()}
