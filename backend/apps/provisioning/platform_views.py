"""
Comptes et rôles d'un espace, gérés depuis les écrans de la plateforme.

Même forme que les routes de l'ERP et de Lumina : la plateforme utilise le
même écran pour toutes ses solutions. L'espace est désigné par son nom
d'adresse (`tenant`, ex. « dev-client1 »), celui que la plateforme a
enregistré pour l'abonnement.

    GET    platform/tenant-status/?tenant=     a-t-il un administrateur ?
    POST   platform/tenant/                    ouvrir l'espace (adresse choisie), sans compte
    POST   platform/bootstrap-admin/           premier administrateur — crée l'espace s'il n'existe pas
    GET    platform/accounts/?tenant=          comptes et rôles
    POST   platform/accounts/                  ajouter un compte
    PATCH  platform/accounts/<id>/             mot de passe, rôle, état
    GET    platform/roles/?tenant=             rôles, leurs permissions, et le catalogue des permissions
    POST   platform/roles/                     créer un rôle
    PATCH  platform/roles/<key>/               renommer, changer ses permissions
    DELETE platform/roles/<key>/?tenant=       supprimer un rôle sans compte

Signé comme le reste de l'API interne (HMAC, voir signing.py).
"""

import re

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from apps.audit.services import actor_of, record
from apps.core import solution
from apps.entitlements.services import ensure_default_modules
from apps.identity.models import Account
from apps.identity.services import AccountError, bootstrap_admin, create_account, update_account
from apps.rbac.models import Role
from apps.rbac.services import ensure_default_roles
from apps.tenancy.models import Domain, Tenant, slug_validator

from .views import SignedPlatformView, idempotent

_TENANT = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_ROLE_KEY = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


def refus(message, code=400, error_code="invalid"):
    return Response({"detail": message, "code": error_code}, status=code)


def compte(account: Account) -> dict:
    """Même forme que les comptes de l'ERP. Jamais le mot de passe, même haché."""
    initiales = "".join(p[0] for p in account.display_name.split()[:2]).upper() or account.username[:2].upper()
    return {
        "id": str(account.pk),
        "name": account.display_name,
        "username": account.username,
        "email": account.email,
        "role": account.role.key,
        "status": "actif" if account.is_active else "inactif",
        "initials": initiales[:4],
        "lastLogin": account.user.last_login.isoformat() if account.user.last_login else "",
    }


def role_choice(role: Role) -> dict:
    tout = "*" in (role.permissions or [])
    return {
        "value": role.key,
        "label": role.label,
        "description": "Toutes les permissions" if tout else f"{len(role.permissions or [])} permission(s)",
    }


def role_detail(role: Role) -> dict:
    return {
        **role_choice(role),
        "permissions": list(role.permissions or []),
        "is_system": role.is_system,
        "accounts": role.accounts.count(),
    }


def permission_catalog() -> list[dict]:
    catalogue = [{"key": "*", "label": "Toutes les permissions", "module": ""}]
    for key, label in solution.PERMISSIONS.items():
        module = key.split(".", 1)[0]
        catalogue.append({"key": key, "label": label, "module": module if module in solution.MODULES else ""})
    for module, spec in solution.MODULES.items():
        catalogue.append({"key": f"{module}.*", "label": f"Tout le module {spec['label']}", "module": module})
    return catalogue


def _valider_permissions(permissions) -> list[str] | None:
    if not isinstance(permissions, list):
        return None
    connues = {p["key"] for p in permission_catalog()}
    propres = sorted({str(p) for p in permissions})
    return propres if all(p in connues for p in propres) else None


class TenantPlatformView(SignedPlatformView):
    def tenant(self, request):
        source = request.query_params if request.method in ("GET", "DELETE") else request.data
        slug = str(source.get("tenant", "")).strip().lower()
        if not _TENANT.match(slug):
            return None
        return Tenant.objects.filter(slug=slug).first()


class TenantStatusView(TenantPlatformView):
    def get(self, request):
        tenant = self.tenant(request)
        return Response({"has_admin": bool(tenant) and Account.objects.filter(tenant=tenant).exists()})


def ouvrir_espace(slug: str, company: str, actor: str) -> tuple[Tenant, bool]:
    """L'espace `slug`, créé s'il n'existe pas : adresse, rôles, modules."""
    tenant, created = Tenant.objects.get_or_create(slug=slug, defaults={"display_name": company or slug})
    if created:
        Domain.objects.get_or_create(
            hostname=f"{slug}.{settings.ROOT_DOMAIN}", defaults={"tenant": tenant, "is_primary": True}
        )
        ensure_default_roles(tenant)
        ensure_default_modules(tenant)
        record("tenant.provisioned", tenant=tenant, actor=actor, target=tenant)
    return tenant, created


class TenantOpenView(TenantPlatformView):
    """Ouvre l'espace dès que le client a choisi son adresse, avant tout compte.

    Sans cela, l'adresse répondait « aucun espace » jusqu'au premier compte.
    Sans effet si l'espace existe déjà.
    """

    @idempotent
    def post(self, request):
        slug = str(request.data.get("tenant", "")).strip().lower()
        try:
            slug_validator(slug)
        except Exception:
            return refus("Nom d'espace invalide.")
        with transaction.atomic():
            tenant, created = ouvrir_espace(slug, str(request.data.get("company", "")).strip(), actor_of(request))
        return Response({"tenant": tenant.slug, "created": created}, status=201 if created else 200)


class BootstrapAdminView(TenantPlatformView):
    """Premier administrateur. Crée l'espace à la volée quand la plateforme ne l'a pas encore provisionné."""

    @idempotent
    def post(self, request):
        slug = str(request.data.get("tenant", "")).strip().lower()
        try:
            slug_validator(slug)
        except Exception:
            return refus("Nom d'espace invalide.")
        with transaction.atomic():
            tenant, _ = ouvrir_espace(slug, str(request.data.get("company", "")).strip(), actor_of(request))
            try:
                account = bootstrap_admin(
                    tenant,
                    name=request.data.get("name"),
                    username=request.data.get("username"),
                    email=request.data.get("email"),
                    password=str(request.data.get("password", "")),
                )
            except AccountError as exc:
                transaction.set_rollback(True)
                return refus(exc.message, exc.status, exc.code)
        record("account.bootstrap_admin", tenant=tenant, actor=actor_of(request), target=account)
        return Response({"detail": "Compte administrateur créé.", "user": compte(account)}, status=201)


class AccountsView(TenantPlatformView):
    def get(self, request):
        tenant = self.tenant(request)
        if tenant is None:
            return Response({"accounts": [], "roles": []})
        comptes = Account.objects.for_tenant(tenant).select_related("role", "user")
        return Response({
            "accounts": [compte(a) for a in comptes],
            "roles": [role_choice(r) for r in Role.objects.for_tenant(tenant).order_by("label")],
        })

    @idempotent
    def post(self, request):
        tenant = self.tenant(request)
        if tenant is None:
            return refus("Espace introuvable : créez d'abord son administrateur.", 404, "tenant_not_found")
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
            return refus(exc.message, exc.status, exc.code)
        record("account.created", tenant=tenant, actor=actor_of(request), target=account, role=account.role.key)
        return Response(compte(account), status=201)


class AccountView(TenantPlatformView):
    @idempotent
    def patch(self, request, pk):
        tenant = self.tenant(request)
        account = Account.objects.for_tenant(tenant).filter(pk=pk).first() if tenant else None
        if account is None:
            return refus("Compte introuvable.", 404, "account_not_found")
        etat = str(request.data.get("status", "")).strip()
        try:
            changed = update_account(
                account,
                password=str(request.data.get("password", "")) or None,
                role=str(request.data.get("role", "")).strip() or None,
                status={"actif": "active", "inactif": "inactive"}.get(etat, etat) or None,
            )
        except AccountError as exc:
            return refus(exc.message, exc.status, exc.code)
        record("account.updated", tenant=tenant, actor=actor_of(request), target=account, changed=changed)
        account.refresh_from_db()
        return Response(compte(account))


def _gestionnaire_restant(tenant, role: Role, permissions: list[str]) -> bool:
    """Après ce changement, un compte actif pourra-t-il encore gérer les accès ?"""
    for account in Account.objects.for_tenant(tenant).select_related("role", "user"):
        if not account.is_active:
            continue
        perms = permissions if account.role_id == role.pk else account.role.permissions
        if any(p in ("*", "accounts.manage", "accounts.*") for p in perms or []):
            return True
    return False


class RolesView(TenantPlatformView):
    def get(self, request):
        tenant = self.tenant(request)
        roles = Role.objects.for_tenant(tenant).order_by("label") if tenant else []
        return Response({
            "roles": [role_detail(r) for r in roles],
            "permissions": permission_catalog(),
        })

    @idempotent
    def post(self, request):
        tenant = self.tenant(request)
        if tenant is None:
            return refus("Espace introuvable.", 404, "tenant_not_found")
        key = str(request.data.get("key", "")).strip().lower()
        label = str(request.data.get("label", "")).strip()
        permissions = _valider_permissions(request.data.get("permissions", []))
        if not _ROLE_KEY.match(key) or not label:
            return refus("Clé (minuscules, chiffres, tirets) et nom du rôle requis.")
        if permissions is None:
            return refus("Permissions inconnues.", error_code="unknown_permission")
        if Role.objects.filter(tenant=tenant, key=key).exists():
            return refus("Ce rôle existe déjà.", 409, "role_exists")
        role = Role.objects.create(tenant=tenant, key=key, label=label[:120], permissions=permissions)
        record("role.created", tenant=tenant, actor=actor_of(request), target=role, permissions=permissions)
        return Response(role_detail(role), status=201)


class RoleView(TenantPlatformView):
    def _role(self, request, key):
        tenant = self.tenant(request)
        role = Role.objects.filter(tenant=tenant, key=key).first() if tenant else None
        return tenant, role

    @idempotent
    def patch(self, request, key):
        tenant, role = self._role(request, key)
        if role is None:
            return refus("Rôle introuvable.", 404, "role_not_found")
        champs = []
        if "permissions" in request.data:
            permissions = _valider_permissions(request.data.get("permissions"))
            if permissions is None:
                return refus("Permissions inconnues.", error_code="unknown_permission")
            if not _gestionnaire_restant(tenant, role, permissions):
                # Retirer la gestion des comptes au dernier rôle qui l'a
                # fermerait l'espace à tout le monde.
                return refus("Plus aucun compte actif ne pourrait gérer les accès de l'espace.", 409, "last_admin")
            role.permissions = permissions
            champs.append("permissions")
        label = str(request.data.get("label", "")).strip()
        if label:
            role.label = label[:120]
            champs.append("label")
        if not champs:
            return refus("Rien à modifier.", error_code="nothing_to_change")
        role.save(update_fields=champs)
        record("role.updated", tenant=tenant, actor=actor_of(request), target=role,
               permissions=role.permissions)
        return Response(role_detail(role))

    @idempotent
    def delete(self, request, key):
        tenant, role = self._role(request, key)
        if role is None:
            return refus("Rôle introuvable.", 404, "role_not_found")
        if role.is_system:
            return refus("Un rôle de base ne se supprime pas ; ses permissions se modifient.", 409, "system_role")
        if role.accounts.exists():
            return refus("Des comptes ont encore ce rôle : changez-le d'abord.", 409, "role_in_use")
        role.delete()
        record("role.deleted", tenant=tenant, actor=actor_of(request), role=key)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Démonstration --------------------------------------------------------------


def _etat_demo(tenant) -> dict:
    from .demo import compter
    from .models import DemoSnapshot

    snapshot = DemoSnapshot.objects.filter(tenant=tenant).first()
    return {
        "tenant": tenant.slug,
        "is_demo": tenant.is_demo,
        "snapshot_at": snapshot.updated_at.isoformat() if snapshot else None,
        "rows": compter(tenant),
    }


class DemoView(TenantPlatformView):
    """GET : état de la démo. POST : l'ouvrir (espace marqué démo, données d'exemple s'il est vide)."""

    def get(self, request):
        tenant = self.tenant(request)
        if tenant is None:
            return refus("Démo introuvable.", 404, "tenant_not_found")
        return Response(_etat_demo(tenant))

    @idempotent
    def post(self, request):
        slug = str(request.data.get("tenant", "")).strip().lower()
        try:
            slug_validator(slug)
        except Exception:
            return refus("Nom d'espace invalide.")
        with transaction.atomic():
            tenant, created = ouvrir_espace(slug, str(request.data.get("company", "")).strip(), actor_of(request))
            if not tenant.is_demo:
                if not created and Account.objects.filter(tenant=tenant).exists():
                    # Un vrai espace ne devient jamais une démo : elle serait
                    # remise à zéro chaque nuit.
                    return refus("Cet espace existe déjà et n'est pas une démo.", 409, "not_demo")
                tenant.is_demo = True
                tenant.save(update_fields=["is_demo", "updated_at"])
            from .demo import compter

            if not compter(tenant).keys() - {"identity.Account", "rbac.Role", "entitlements.TenantModule"}:
                solution.seed_demo(tenant)
        record("demo.opened", tenant=tenant, actor=actor_of(request), target=tenant)
        return Response(_etat_demo(tenant), status=201 if created else 200)


class DemoSnapshotView(TenantPlatformView):
    """Enregistre l'état actuel de la démo comme référence."""

    @idempotent
    def post(self, request):
        from .demo import DemoError, capturer

        tenant = self.tenant(request)
        if tenant is None:
            return refus("Démo introuvable.", 404, "tenant_not_found")
        try:
            snapshot = capturer(tenant)
        except DemoError as exc:
            return refus(exc.message, exc.status, exc.code)
        record("demo.snapshot", tenant=tenant, actor=actor_of(request), target=tenant, rows=len(snapshot.data))
        return Response(_etat_demo(tenant))


class DemoResetView(TenantPlatformView):
    """Remet la démo dans l'état de sa référence."""

    @idempotent
    def post(self, request):
        from .demo import DemoError, restaurer

        tenant = self.tenant(request)
        if tenant is None:
            return refus("Démo introuvable.", 404, "tenant_not_found")
        try:
            resultat = restaurer(tenant)
        except DemoError as exc:
            return refus(exc.message, exc.status, exc.code)
        record("demo.reset", tenant=tenant, actor=actor_of(request), target=tenant, **resultat)
        return Response({**_etat_demo(tenant), **resultat})
