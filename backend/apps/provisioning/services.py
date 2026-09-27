from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.core import solution
from apps.entitlements.services import (
    StaleRevision,
    UnknownModule,
    apply_entitlements,
    ensure_default_modules,
)
from apps.rbac.services import ensure_default_roles
from apps.tenancy.models import Domain, Tenant, TenantModel, normalize_host

from .contracts import DemoResetRequest, TenantProvisionRequest
from .models import Job


class ProvisioningError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "invalid"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


@transaction.atomic
def provision_tenant(payload: TenantProvisionRequest, *, actor: str) -> tuple[Tenant, bool]:
    """Crée ou met à jour un espace. Renvoie (espace, créé).

    Pose tout ce qu'il faut pour que l'espace s'ouvre utilisable : rôles par
    défaut, modules, adresses. Le compte du propriétaire n'est PAS créé ici :
    le contrat ne transporte pas de mot de passe. Il le crée lui-même depuis
    la plateforme (bootstrap-admin), une seule fois.
    """
    data = payload.tenant
    tenant = Tenant.objects.select_for_update().filter(external_id=data.external_id).first()
    created = tenant is None
    conflit = Tenant.objects.filter(slug=data.slug).exclude(external_id=data.external_id)
    if conflit.exists():
        raise ProvisioningError("Ce nom d'espace est déjà pris.", 409, "slug_taken")

    if created:
        tenant = Tenant(external_id=data.external_id)
    tenant.slug = data.slug
    tenant.display_name = data.display_name
    tenant.is_demo = data.is_demo
    tenant.owner_name = payload.owner.name
    tenant.owner_email = payload.owner.email
    if payload.template:
        tenant.template_key = payload.template.key
        tenant.template_version = payload.template.version
    tenant.save()

    _set_domains(tenant, payload.domains.platform_hostname, payload.domains.custom_hostnames)
    ensure_default_roles(tenant)
    ensure_default_modules(tenant)
    try:
        apply_entitlements(
            tenant,
            revision=payload.subscription.revision,
            modules=[m.model_dump() for m in payload.subscription.modules],
            limits=payload.subscription.limits,
            plan_key=payload.subscription.plan_key,
        )
    except StaleRevision:
        # Un nouveau provisionnement (changement de nom, d'adresse) peut
        # porter une révision dépassée par une mise à jour des droits faite
        # entre-temps : les droits plus récents restent.
        pass
    except UnknownModule as exc:
        raise ProvisioningError(str(exc), 400, "unknown_module") from exc
    if created and tenant.is_demo:
        resume = solution.seed_demo(tenant)
        record("tenant.demo_seeded", tenant=tenant, actor=actor, target=tenant, **resume)

    record(
        "tenant.provisioned" if created else "tenant.updated",
        tenant=tenant, actor=actor, target=tenant, event_id=str(payload.event_id),
    )
    return tenant, created


def _set_domains(tenant, primary: str, extra: list[str]) -> None:
    wanted = [normalize_host(primary)] + [normalize_host(h) for h in extra]
    pris = Domain.objects.filter(hostname__in=wanted).exclude(tenant=tenant)
    if pris.exists():
        raise ProvisioningError(
            f"Adresse déjà attribuée à un autre espace : {pris.first().hostname}.", 409, "host_taken"
        )
    Domain.objects.filter(tenant=tenant).exclude(hostname__in=wanted).delete()
    for hostname in wanted:
        Domain.objects.update_or_create(
            hostname=hostname, defaults={"tenant": tenant, "is_primary": hostname == wanted[0]}
        )


def tenant_models() -> list[type[TenantModel]]:
    """Toutes les tables rattachées à un espace — celles qu'une réinitialisation vide."""
    return [
        model for model in django_apps.get_models()
        if issubclass(model, TenantModel)
    ]


def demo_reset(tenant: Tenant, payload: DemoResetRequest, *, actor: str) -> Job:
    """Remet un espace de démonstration dans son état de départ.

    Réservé aux espaces `is_demo` : c'est une suppression. Seules les lignes
    de CET espace sont effacées ; les comptes, les rôles et les modules
    restent, pour que la démonstration se rouvre avec les mêmes accès.
    """
    if not tenant.is_demo:
        raise ProvisioningError(
            "Seul un espace de démonstration peut être réinitialisé.", 409, "not_demo"
        )
    if payload.expected_current_version and payload.expected_current_version != tenant.template_version:
        raise ProvisioningError(
            "L'espace n'est plus à la version attendue.", 409, "version_mismatch"
        )

    job = Job.objects.create(tenant=tenant, action="reset_demo")
    garder = {"Account", "Role", "TenantModule"}
    try:
        with transaction.atomic():
            supprime = {}
            for model in tenant_models():
                if model.__name__ in garder:
                    continue
                count, _ = model._base_manager.filter(tenant=tenant).delete()
                if count:
                    supprime[model._meta.label] = count
            resume = solution.seed_demo(tenant)
            tenant.template_key = payload.template.key
            tenant.template_version = payload.template.version
            tenant.save(update_fields=["template_key", "template_version", "updated_at"])
        job.status, job.result = "succeeded", {"deleted": supprime, "seeded": resume}
    except Exception:
        job.status, job.error_code = "failed", "reset_failed"
        raise
    finally:
        job.finished_at = timezone.now()
        job.save()
        record("tenant.demo_reset", tenant=tenant, actor=actor, target=tenant,
               status=job.status, template=f"{payload.template.key}@{payload.template.version}")
    return job
