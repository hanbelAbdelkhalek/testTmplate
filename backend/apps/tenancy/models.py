import uuid

from django.core.validators import RegexValidator
from django.db import models

slug_validator = RegexValidator(
    regex=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    message="Minuscules, chiffres et tirets ; ni au début ni à la fin.",
)


class Tenant(models.Model):
    """L'espace d'un client dans cette solution.

    Créé par la plateforme (`/api/internal/v1/tenants/provision/`), jamais par
    le client lui-même. `external_id` est l'identifiant que la plateforme lui
    a donné : c'est par lui qu'elle le désigne ensuite, pas par son nom, qui
    peut changer.
    """

    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_CHOICES = ((STATUS_ACTIVE, "Actif"), (STATUS_SUSPENDED, "Suspendu"))

    external_id = models.UUIDField(unique=True, default=uuid.uuid4)
    slug = models.CharField(max_length=63, unique=True, validators=[slug_validator])
    display_name = models.CharField(max_length=180)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    is_demo = models.BooleanField(default=False)

    # Contact du propriétaire tel que la plateforme l'a transmis. Son compte
    # n'existe pas encore : il le crée lui-même (bootstrap-admin), avec un
    # mot de passe que la plateforme ne fait que relayer.
    owner_name = models.CharField(max_length=180, blank=True, default="")
    owner_email = models.EmailField(blank=True, default="")

    # Droits d'abonnement : la plateforme envoie une révision croissante, et
    # une révision plus ancienne que celle-ci est refusée. Sans ce compteur,
    # deux mises à jour arrivées dans le désordre rouvriraient un module
    # qu'on vient de fermer.
    plan_key = models.CharField(max_length=80, blank=True, default="")
    entitlement_revision = models.PositiveBigIntegerField(default=0)

    template_key = models.CharField(max_length=64, blank=True, default="")
    template_version = models.CharField(max_length=40, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self):
        return self.slug

    @property
    def is_active(self) -> bool:
        return self.status == self.STATUS_ACTIVE


def normalize_host(host: str) -> str:
    """`Gestion.SigmaGravity.com:443.` → `gestion.sigmagravity.com`."""
    host = (host or "").split(",")[0].strip().lower()
    if host.startswith("["):  # IPv6 littérale
        return host
    return host.split(":")[0].rstrip(".")


class Domain(models.Model):
    """Un nom d'hôte qui mène à un espace.

    La plateforme choisit les noms (« gestion.sigmagravity.com »,
    « dev-gestion.sigmagravity.com », un domaine personnalisé) : la solution
    ne les devine pas en découpant un préfixe, elle les reçoit et les cherche
    tels quels. Deviner, c'est risquer qu'un nom mal découpé ouvre l'espace
    d'un autre.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="domains")
    hostname = models.CharField(max_length=253, unique=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "hostname"]

    def __str__(self):
        return self.hostname

    def save(self, *args, **kwargs):
        self.hostname = normalize_host(self.hostname)
        super().save(*args, **kwargs)


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        # Un espace absent ne donne rien, jamais tout : une erreur de câblage
        # doit se voir comme une liste vide, pas comme une fuite.
        if tenant is None:
            return self.none()
        return self.filter(tenant=tenant)


class TenantModel(models.Model):
    """Base de TOUTE table métier.

    - `tenant` est obligatoire et indexé : une ligne appartient toujours à un
      espace.
    - Une unicité métier (référence, code, slug…) se déclare PAR ESPACE :
          constraints = [models.UniqueConstraint(
              fields=["tenant", "sku"], name="catalog_item_sku_par_espace")]
      jamais `unique=True` sur le champ seul — sinon le deuxième client ne
      peut pas réutiliser une référence prise par le premier.
    - Tout code qui cherche un nom libre cherche DANS l'espace :
          Item.objects.for_tenant(t).filter(slug=candidat).exists()

    Les sous-classes sont effacées par la réinitialisation d'un espace de
    démonstration (voir apps/provisioning/services.py).
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+")

    objects = TenantQuerySet.as_manager()

    class Meta:
        abstract = True
