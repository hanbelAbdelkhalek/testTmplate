"""
MODULE D'EXEMPLE — à garder comme modèle, puis à remplacer par le métier.

Il montre tout ce qu'un module doit faire : table rattachée à l'espace,
unicité par espace, vue cloisonnée, module d'abonnement, permissions,
limite, données de démonstration, tests d'isolation.
"""

from django.db import models

from apps.tenancy.models import TenantModel


class Item(TenantModel):
    sku = models.CharField("référence", max_length=64)
    name = models.CharField("nom", max_length=200)
    price = models.DecimalField("prix", max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            # Par espace : deux clients peuvent chacun avoir leur « REF-001 ».
            models.UniqueConstraint(fields=["tenant", "sku"], name="catalog_item_sku_par_espace")
        ]

    def __str__(self):
        return f"{self.sku} — {self.name}"
