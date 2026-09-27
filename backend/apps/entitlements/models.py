from django.db import models

from apps.tenancy.models import TenantModel


class TenantModule(TenantModel):
    """Un module de solution.MODULES, ouvert ou fermé pour un espace, et ses plafonds.

    Écrit par la plateforme uniquement (droits d'abonnement). Un client ne
    peut pas s'ouvrir lui-même ce qu'il n'a pas acheté.
    """

    key = models.SlugField(max_length=64)
    enabled = models.BooleanField(default=True)
    # {"max_items": 500}. Une clé absente prend la valeur par défaut de
    # solution.MODULES ; None veut dire illimité.
    limits = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "key"], name="entitlements_module_par_espace"
            )
        ]

    def __str__(self):
        return f"{self.tenant_id}:{self.key}={'on' if self.enabled else 'off'}"
