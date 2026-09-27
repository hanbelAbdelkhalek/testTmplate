"""
Les règles des comptes, en un seul endroit.

Deux chemins y mènent : l'écran « Équipe » de l'espace (le client gère ses
comptes) et l'API interne de la plateforme (SigmaGravity les gère pour lui).
Les deux passent par ici, pour qu'aucune règle ne diverge — mot de passe,
identifiant unique dans l'espace, dernier administrateur.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core import solution
from apps.rbac.models import Role
from apps.rbac.services import ensure_default_roles

from .models import Account, login_name

User = get_user_model()


class AccountError(Exception):
    """Refus métier : le message est destiné à l'utilisateur, `status` au HTTP."""

    def __init__(self, message: str, status: int = 400, code: str = "invalid"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def _password(password: str, user=None) -> None:
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise AccountError(" ".join(exc.messages), code="weak_password") from exc


def _role(tenant, key: str) -> Role:
    role = Role.objects.filter(tenant=tenant, key=key).first()
    if role is None:
        keys = ", ".join(Role.objects.filter(tenant=tenant).values_list("key", flat=True))
        raise AccountError(f"Rôle inconnu. Attendu : {keys}.", code="unknown_role")
    return role


def _clean(value) -> str:
    return str(value or "").strip()


@transaction.atomic
def create_account(tenant, *, name, username, email, password, role=None) -> Account:
    name, username, email = _clean(name), _clean(username).lower(), _clean(email)
    if not (name and username and email and password):
        raise AccountError("Nom, identifiant, e-mail et mot de passe sont requis.")
    if not username.replace(".", "").replace("-", "").replace("_", "").isalnum():
        raise AccountError(
            "L'identifiant ne contient que des lettres, chiffres, points, tirets et soulignés.",
            code="invalid_username",
        )
    role_obj = _role(tenant, role or solution.DEFAULT_ROLE)
    if Account.objects.filter(tenant=tenant, username=username).exists():
        raise AccountError("Cet identifiant est déjà pris dans cet espace.", 409, "username_taken")
    _password(password, User(username=username, email=email, first_name=name))
    try:
        # Compte Django et compte d'espace vont de pair : si le second échoue,
        # le premier ne doit pas rester, sinon l'identifiant est pris sans
        # qu'aucun compte ne soit utilisable.
        with transaction.atomic():
            user = User.objects.create_user(
                username=login_name(tenant, username),
                email=email,
                password=password,
                first_name=name[:150],
            )
            return Account.objects.create(
                tenant=tenant,
                user=user,
                username=username,
                display_name=name,
                email=email,
                role=role_obj,
            )
    except IntegrityError as exc:
        raise AccountError("Cet identifiant est déjà pris dans cet espace.", 409, "username_taken") from exc


def bootstrap_admin(tenant, *, name, username, email, password) -> Account:
    """Le premier compte d'un espace, avec le rôle propriétaire.

    Une seule fois : un espace qui a déjà un compte ne peut plus être
    « réclamé » — sinon deviner l'adresse d'un espace suffirait à s'y créer
    un accès administrateur.
    """
    ensure_default_roles(tenant)
    if Account.objects.filter(tenant=tenant).exists():
        raise AccountError("Cet espace a déjà un compte administrateur.", 409, "already_bootstrapped")
    return create_account(
        tenant, name=name, username=username, email=email, password=password,
        role=solution.OWNER_ROLE,
    )


def _is_last_admin(account: Account) -> bool:
    """Reste-t-il un autre compte actif capable de gérer les comptes ?"""
    autres = (
        Account.objects.filter(tenant_id=account.tenant_id, status=Account.STATUS_ACTIVE)
        .exclude(pk=account.pk)
        .select_related("role")
    )
    return not any(a.has_permission("accounts.manage") for a in autres)


@transaction.atomic
def update_account(account: Account, *, password=None, role=None, status=None, name=None) -> list[str]:
    """Modifie un compte. Renvoie la liste de ce qui a changé.

    Le mot de passe se remplace, il ne se lit pas : ni la plateforme ni
    personne ne peut retrouver celui d'un employé.
    """
    account = Account.objects.select_for_update().select_related("role", "user").get(pk=account.pk)
    changed = []
    gestionnaire_avant = account.is_active and account.has_permission("accounts.manage")

    if name:
        account.display_name = _clean(name)
        changed.append("nom")
    if role:
        account.role = _role(account.tenant, _clean(role))
        changed.append("rôle")
    if status:
        if status not in (Account.STATUS_ACTIVE, Account.STATUS_INACTIVE):
            raise AccountError("État attendu : active ou inactive.", code="invalid_status")
        account.status = status
        account.user.is_active = status == Account.STATUS_ACTIVE
        changed.append("état")
    if password:
        _password(password, account.user)
        account.user.set_password(password)
        changed.append("mot de passe")
    if not changed:
        raise AccountError("Rien à modifier.", code="nothing_to_change")

    gestionnaire_apres = account.status == Account.STATUS_ACTIVE and account.role.grants("accounts.manage")
    if gestionnaire_avant and not gestionnaire_apres and _is_last_admin(account):
        # Retirer le dernier gestionnaire fermerait l'espace à tout le monde,
        # sans moyen de le rouvrir depuis l'application.
        raise AccountError(
            "C'est le dernier compte capable de gérer les accès de l'espace.", 409, "last_admin"
        )

    if "mot de passe" in changed or "état" in changed:
        # Les sessions ouvertes tombent : c'est le but quand on change un mot
        # de passe qui a fui, ou qu'on coupe l'accès de quelqu'un qui part.
        account.tokens_valid_after = timezone.now()

    account.user.save()
    account.save()
    return changed


def serialize_account(account: Account) -> dict:
    """Ce qu'on montre d'un compte. Jamais le mot de passe, même haché."""
    return {
        "id": account.pk,
        "username": account.username,
        "name": account.display_name,
        "email": account.email,
        "role": account.role.key,
        "role_label": account.role.label,
        "status": account.status,
        "last_login": account.user.last_login.isoformat() if account.user.last_login else None,
        "created_at": account.created_at.isoformat(),
    }
