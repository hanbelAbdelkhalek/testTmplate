import uuid

from django.db import models


class AuditEvent(models.Model):
    """Ce qui s'est passé, qui l'a fait, sur quoi. Jamais une valeur secrète.

    Immuable : une ligne ne se modifie ni ne se supprime depuis l'application.
    Pas de clé étrangère vers l'espace ni vers le compte : le journal doit
    survivre à leur suppression, c'est souvent là qu'on en a besoin.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    # "account:12", "platform:platform-v1", "system".
    actor = models.CharField(max_length=120)
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=60, blank=True, default="")
    target_id = models.CharField(max_length=100, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Un événement d'audit ne se modifie pas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Un événement d'audit ne se supprime pas.")
