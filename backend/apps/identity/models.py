import math

from django.conf import settings
from django.db import models

from apps.tenancy.models import TenantModel


def login_name(tenant, username: str) -> str:
    """Identifiant Django d'un compte : `<id d'espace>__<identifiant>`.

    `auth.User.username` est unique sur toute la base ; les identifiants, eux,
    doivent l'être par espace — deux clients ont chacun leur « admin ». Le
    préfixe les sépare. L'id plutôt que le slug : un slug peut changer, et
    tous les comptes de l'espace deviendraient inaccessibles.
    """
    return f"{tenant.pk}__{username}"


class Account(TenantModel):
    """Un compte d'un espace client.

    Porté par un `auth.User` Django (mot de passe, dernière connexion) ; ce
    modèle-ci dit à quel espace il appartient, sous quel nom, avec quel rôle.
    Un compte n'existe que dans son espace : son jeton est refusé partout
    ailleurs (voir authentication.py).
    """

    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = ((STATUS_ACTIVE, "Actif"), (STATUS_INACTIVE, "Désactivé"))

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account"
    )
    username = models.CharField(max_length=80)
    display_name = models.CharField(max_length=180)
    email = models.EmailField()
    role = models.ForeignKey("rbac.Role", on_delete=models.PROTECT, related_name="accounts")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    # Tout jeton émis avant cette date est refusé. Posée au changement de mot
    # de passe et à la désactivation : un jeton ne se révoque pas autrement.
    tokens_valid_after = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "username"], name="identity_username_par_espace"
            )
        ]

    def __str__(self):
        return f"{self.tenant_id}:{self.username}"

    @property
    def is_active(self) -> bool:
        return self.status == self.STATUS_ACTIVE and self.user.is_active

    def accepts_token_issued_at(self, iat) -> bool:
        # `iat` est à la seconde : arrondir la date de coupure au-dessus
        # refuse aussi un jeton émis dans la même seconde, juste avant.
        return self.tokens_valid_after is None or (
            iat is not None and int(iat) >= math.ceil(self.tokens_valid_after.timestamp())
        )

    def has_permission(self, permission: str) -> bool:
        return self.role.grants(permission)

    def permissions(self) -> list[str]:
        from apps.core import solution

        return sorted(p for p in solution.PERMISSIONS if self.has_permission(p))
