from django.db import models

from apps.tenancy.models import TenantModel


class Role(TenantModel):
    """Un rôle d'un espace et ce qu'il permet.

    Les rôles de apps/core/solution.py (ROLES) sont posés à la création de
    chaque espace, marqués `is_system` : on peut en changer les droits, pas les
    supprimer, sans quoi des comptes perdraient leur rôle.
    """

    key = models.SlugField(max_length=64)
    label = models.CharField(max_length=120)
    # Liste de permissions : "catalog.view", "catalog.*" ou "*".
    permissions = models.JSONField(default=list, blank=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ["label"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="rbac_role_key_par_espace")
        ]

    def __str__(self):
        return f"{self.tenant_id}:{self.key}"

    def grants(self, permission: str) -> bool:
        module = permission.split(".", 1)[0]
        return any(p in ("*", permission, f"{module}.*") for p in self.permissions or [])
