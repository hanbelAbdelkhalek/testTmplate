import uuid

from django.db import models


class UsedNonce(models.Model):
    """Nonce d'un appel signé déjà vu : un appel intercepté ne se rejoue pas.

    En base plutôt qu'en cache : le cache par défaut est propre à chaque
    processus, et un rejeu envoyé à un autre worker passerait.
    """

    key_id = models.CharField(max_length=80)
    nonce = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key_id", "nonce"], name="provisioning_nonce_unique")
        ]


class IdempotencyRecord(models.Model):
    """Réponse déjà donnée à un `Idempotency-Key`.

    La plateforme renvoie la même clé quand elle réessaie après une coupure :
    elle reçoit la même réponse, et rien n'est créé deux fois. La même clé
    avec un autre contenu est refusée (409) — c'est une erreur, pas un
    nouvel essai.
    """

    key = models.CharField(max_length=128, unique=True)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=300)
    request_hash = models.CharField(max_length=64)
    status_code = models.PositiveSmallIntegerField()
    body = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class Job(models.Model):
    """Trace durable d'une opération demandée par la plateforme."""

    STATUS_CHOICES = (
        ("running", "En cours"),
        ("succeeded", "Réussi"),
        ("failed", "Échoué"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenancy.Tenant", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=40)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="running")
    # Code court et sûr à afficher ; jamais une trace ni un secret.
    error_code = models.CharField(max_length=80, blank=True, default="")
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "action": self.action,
            "status": self.status,
            "error_code": self.error_code,
            "result": self.result,
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
