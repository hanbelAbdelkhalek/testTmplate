"""
API interne : ce que la plateforme SigmaGravity appelle, signé (HMAC).

Jamais depuis un navigateur. Le frontend refuse de relayer /api/internal/, et
nginx n'expose pas Django : seule la plateforme, sur le réseau Docker, y
arrive — et encore faut-il la signature.

    POST  tenants/provision/                         créer / mettre à jour un espace
    GET   tenants/<external_id>/                     état de l'espace
    PATCH tenants/<external_id>/                     suspendre / réactiver, renommer
    GET   tenants/<external_id>/entitlements/        modules, limites, consommation
    PUT   tenants/<external_id>/entitlements/        appliquer ce qui a été vendu
    POST  tenants/<external_id>/bootstrap-admin/     premier compte (une seule fois)
    GET   tenants/<external_id>/accounts/            comptes et rôles
    POST  tenants/<external_id>/accounts/            ajouter un compte
    PATCH tenants/<external_id>/accounts/<id>/       mot de passe, rôle, état
    POST  tenants/<external_id>/demo-reset/          réinitialiser une démo
    GET   jobs/<id>/                                 état d'une opération
"""

import hashlib
import json
from functools import wraps

from django.conf import settings
from pydantic import ValidationError as ContractError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import actor_of, record
from apps.entitlements.services import (
    StaleRevision,
    UnknownModule,
    apply_entitlements,
    entitlement_state,
)
from apps.identity.models import Account
from apps.identity.services import (
    AccountError,
    bootstrap_admin,
    create_account,
    serialize_account,
    update_account,
)
from apps.rbac.models import Role
from apps.tenancy.models import Tenant

from .contracts import DemoResetRequest, EntitlementUpdateRequest, TenantProvisionRequest
from .models import IdempotencyRecord, Job
from .services import ProvisioningError, demo_reset, provision_tenant
from .signing import SignatureError, SignatureNotConfigured, verify


class PlatformAuthFailed(APIException):
    # APIException plutôt qu'AuthenticationFailed : sans authentificateur
    # déclaré, DRF transformerait celle-ci en 403.
    status_code = 401
    default_detail = "Appel non autorisé."
    default_code = "signature_invalid"


class NotConfigured(APIException):
    status_code = 503
    default_detail = "Provisionnement non configuré sur ce serveur."
    default_code = "signature_not_configured"


def fail(message: str, status_code: int, code: str) -> Response:
    return Response({"detail": message, "code": code}, status=status_code)


def idempotent(handler):
    """Même `Idempotency-Key`, même contenu → même réponse, sans refaire l'opération."""

    @wraps(handler)
    def wrapper(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key", "")
        empreinte = hashlib.sha256(
            request.method.encode() + b"\n" + request.get_full_path().encode() + b"\n" + request.body
        ).hexdigest()
        deja = IdempotencyRecord.objects.filter(key=key).first()
        if deja is not None:
            if deja.request_hash != empreinte:
                return fail(
                    "Cette clé d'idempotence a déjà servi pour un autre appel.",
                    409, "idempotency_conflict",
                )
            response = Response(None if deja.status_code == 204 else deja.body, status=deja.status_code)
            response["Idempotent-Replayed"] = "true"
            return response
        response = handler(self, request, *args, **kwargs)
        # Une erreur serveur peut réussir au prochain essai : on ne la fige pas.
        if response.status_code < 500:
            IdempotencyRecord.objects.get_or_create(
                key=key,
                defaults={
                    "method": request.method,
                    "path": request.get_full_path()[:300],
                    "request_hash": empreinte,
                    "status_code": response.status_code,
                    # Une réponse sans corps (204) n'a rien à rejouer.
                    "body": response.data if response.data is not None else {},
                },
            )
        return response

    return wrapper


def parse(model, request):
    """Valide le corps contre le contrat. Renvoie (objet, None) ou (None, réponse 400)."""
    try:
        payload = model.model_validate_json(request.body or b"{}")
    except ContractError as exc:
        erreurs = json.loads(exc.json(include_input=False, include_url=False))
        return None, Response(
            {"detail": "Contenu non conforme au contrat.", "code": "contract_invalid", "errors": erreurs},
            status=400,
        )
    solution = getattr(payload, "solution", None)
    if solution and (solution.key != settings.SOLUTION_KEY or solution.environment != settings.ENVIRONMENT):
        # Un appel destiné à une autre solution ou à l'autre pile — une
        # erreur de routage à arrêter avant qu'elle n'écrive quoi que ce soit.
        return None, fail(
            f"Appel destiné à {solution.key}/{solution.environment}, reçu par "
            f"{settings.SOLUTION_KEY}/{settings.ENVIRONMENT}.",
            409, "wrong_solution",
        )
    return payload, None


class SignedPlatformView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        try:
            request.platform_key_id = verify(request._request)
        except SignatureNotConfigured as exc:
            raise NotConfigured() from exc
        except SignatureError as exc:
            # Message générique : le détail n'aiderait qu'un attaquant.
            raise PlatformAuthFailed(code=exc.code) from exc

    def tenant(self, external_id) -> Tenant:
        tenant = Tenant.objects.filter(external_id=external_id).first()
        if tenant is None:
            raise _NotFound()
        return tenant


class _NotFound(APIException):
    status_code = 404
    default_detail = "Espace introuvable."
    default_code = "tenant_not_found"


def tenant_state(tenant: Tenant) -> dict:
    return {
        "external_id": str(tenant.external_id),
        "slug": tenant.slug,
        "display_name": tenant.display_name,
        "status": tenant.status,
        "is_demo": tenant.is_demo,
        "domains": list(tenant.domains.values_list("hostname", flat=True)),
        "has_admin": Account.objects.filter(tenant=tenant).exists(),
        "entitlement_revision": tenant.entitlement_revision,
        "template": {"key": tenant.template_key, "version": tenant.template_version},
    }


class ProvisionView(SignedPlatformView):
    @idempotent
    def post(self, request):
        payload, erreur = parse(TenantProvisionRequest, request)
        if erreur:
            return erreur
        try:
            tenant, created = provision_tenant(payload, actor=actor_of(request))
        except ProvisioningError as exc:
            return fail(exc.message, exc.status, exc.code)
        return Response(tenant_state(tenant), status=201 if created else 200)


class TenantView(SignedPlatformView):
    def get(self, request, external_id):
        return Response(tenant_state(self.tenant(external_id)))

    @idempotent
    def patch(self, request, external_id):
        tenant = self.tenant(external_id)
        champs = []
        etat = str(request.data.get("status", "")).strip()
        if etat:
            if etat not in (Tenant.STATUS_ACTIVE, Tenant.STATUS_SUSPENDED):
                return fail("État attendu : active ou suspended.", 400, "invalid_status")
            tenant.status = etat
            champs.append("status")
        nom = str(request.data.get("display_name", "")).strip()
        if nom:
            tenant.display_name = nom[:180]
            champs.append("display_name")
        if not champs:
            return fail("Rien à modifier.", 400, "nothing_to_change")
        tenant.save(update_fields=[*champs, "updated_at"])
        record("tenant.updated", tenant=tenant, actor=actor_of(request), target=tenant, fields=champs)
        return Response(tenant_state(tenant))


class EntitlementsView(SignedPlatformView):
    def get(self, request, external_id):
        return Response(entitlement_state(self.tenant(external_id)))

    @idempotent
    def put(self, request, external_id):
        tenant = self.tenant(external_id)
        payload, erreur = parse(EntitlementUpdateRequest, request)
        if erreur:
            return erreur
        if payload.tenant_external_id != tenant.external_id:
            return fail("L'espace du corps ne correspond pas à l'adresse.", 400, "tenant_mismatch")
        try:
            applied = apply_entitlements(
                tenant,
                revision=payload.subscription.revision,
                modules=[m.model_dump() for m in payload.subscription.modules],
                limits=payload.subscription.limits,
                plan_key=payload.subscription.plan_key,
            )
        except StaleRevision as exc:
            return fail(str(exc), 409, "stale_revision")
        except UnknownModule as exc:
            return fail(str(exc), 400, "unknown_module")
        tenant.refresh_from_db()
        if applied:
            record("tenant.entitlements", tenant=tenant, actor=actor_of(request), target=tenant,
                   revision=tenant.entitlement_revision)
        return Response({**entitlement_state(tenant), "applied": applied})


class BootstrapAdminView(SignedPlatformView):
    @idempotent
    def post(self, request, external_id):
        tenant = self.tenant(external_id)
        try:
            account = bootstrap_admin(
                tenant,
                name=request.data.get("name"),
                username=request.data.get("username"),
                email=request.data.get("email"),
                password=str(request.data.get("password", "")),
            )
        except AccountError as exc:
            return fail(exc.message, exc.status, exc.code)
        record("account.bootstrap_admin", tenant=tenant, actor=actor_of(request), target=account)
        return Response(
            {"detail": "Compte administrateur créé.", "account": serialize_account(account)},
            status=status.HTTP_201_CREATED,
        )


class PlatformAccountsView(SignedPlatformView):
    def get(self, request, external_id):
        tenant = self.tenant(external_id)
        comptes = Account.objects.for_tenant(tenant).select_related("role", "user")
        return Response(
            {
                "accounts": [serialize_account(a) for a in comptes],
                "roles": [{"key": r.key, "label": r.label} for r in Role.objects.for_tenant(tenant)],
            }
        )

    @idempotent
    def post(self, request, external_id):
        tenant = self.tenant(external_id)
        try:
            account = create_account(
                tenant,
                name=request.data.get("name"),
                username=request.data.get("username"),
                email=request.data.get("email"),
                password=str(request.data.get("password", "")),
                role=str(request.data.get("role", "")).strip() or None,
            )
        except AccountError as exc:
            return fail(exc.message, exc.status, exc.code)
        record("account.created", tenant=tenant, actor=actor_of(request), target=account,
               role=account.role.key)
        return Response(serialize_account(account), status=status.HTTP_201_CREATED)


class PlatformAccountView(SignedPlatformView):
    @idempotent
    def patch(self, request, external_id, pk):
        tenant = self.tenant(external_id)
        account = Account.objects.for_tenant(tenant).filter(pk=pk).first()
        if account is None:
            return fail("Compte introuvable.", 404, "account_not_found")
        try:
            changed = update_account(
                account,
                password=str(request.data.get("password", "")) or None,
                role=str(request.data.get("role", "")).strip() or None,
                status=str(request.data.get("status", "")).strip() or None,
                name=str(request.data.get("name", "")).strip() or None,
            )
        except AccountError as exc:
            return fail(exc.message, exc.status, exc.code)
        record("account.updated", tenant=tenant, actor=actor_of(request), target=account,
               changed=changed)
        account.refresh_from_db()
        return Response(serialize_account(account))


class DemoResetView(SignedPlatformView):
    @idempotent
    def post(self, request, external_id):
        tenant = self.tenant(external_id)
        payload, erreur = parse(DemoResetRequest, request)
        if erreur:
            return erreur
        if payload.tenant_external_id != tenant.external_id:
            return fail("L'espace du corps ne correspond pas à l'adresse.", 400, "tenant_mismatch")
        try:
            job = demo_reset(tenant, payload, actor=actor_of(request))
        except ProvisioningError as exc:
            return fail(exc.message, exc.status, exc.code)
        return Response(job.as_dict(), status=status.HTTP_202_ACCEPTED)


class JobView(SignedPlatformView):
    def get(self, request, job_id):
        job = Job.objects.filter(pk=job_id).first()
        if job is None:
            return fail("Opération introuvable.", 404, "job_not_found")
        return Response(job.as_dict())
