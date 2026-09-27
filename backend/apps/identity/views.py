from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import actor_of, record
from apps.entitlements.services import entitlement_state
from apps.rbac.models import Role

from .authentication import TENANT_CLAIM, check_account, tokens_for
from .models import Account, login_name
from .throttles import LoginThrottle
from .services import AccountError, create_account, serialize_account, update_account


def refus(exc: AccountError) -> Response:
    return Response({"detail": exc.message, "code": exc.code}, status=exc.status)


class LoginView(APIView):
    """Connexion à l'espace de l'adresse visitée, et à lui seul.

    L'identifiant est cherché dans l'espace résolu par le middleware : le même
    « admin » tapé sur l'adresse de deux clients ouvre deux comptes
    différents, ou aucun.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    def post(self, request):
        tenant = request.tenant
        username = str(request.data.get("username", "")).strip().lower()
        password = str(request.data.get("password", ""))
        user = authenticate(request, username=login_name(tenant, username), password=password)
        account = getattr(user, "account", None) if user else None
        if account is None or account.tenant_id != tenant.pk or not account.is_active:
            # Même message pour un identifiant inconnu, un mauvais mot de passe
            # ou un compte désactivé : ne pas dire lequel.
            return Response(
                {"detail": "Identifiant ou mot de passe incorrect.", "code": "invalid_credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        record("account.login", tenant=tenant, actor=f"account:{account.pk}", target=account)
        return Response(tokens_for(account))


class RefreshView(APIView):
    """Nouveau jeton d'accès, pour le même espace et un compte toujours actif."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        try:
            refresh = RefreshToken(str(request.data.get("refresh", "")))
        except TokenError:
            return Response(
                {"detail": "Session expirée. Reconnectez-vous.", "code": "token_invalid"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        tenant = request.tenant
        if refresh.get(TENANT_CLAIM) != tenant.pk:
            return Response(
                {"detail": "Jeton émis pour un autre espace.", "code": "wrong_tenant"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        account = Account.objects.select_related("user").filter(user_id=refresh.get("user_id")).first()
        try:
            check_account(account, tenant, refresh)
        except AuthenticationFailed as exc:
            return Response({"detail": str(exc.detail), "code": "token_revoked"}, status=401)
        return Response({"access": str(refresh.access_token)})


class MeView(APIView):
    """Le compte connecté, son espace, ses droits et les modules ouverts.

    C'est ce que le frontend lit pour construire le menu. Un affichage : les
    vraies vérifications restent côté serveur, à chaque appel.
    """

    def get(self, request):
        account = request.user.account
        return Response(
            {
                "account": serialize_account(account),
                "permissions": account.permissions(),
                "tenant": {
                    "slug": request.tenant.slug,
                    "name": request.tenant.display_name,
                    "is_demo": request.tenant.is_demo,
                },
                "entitlements": entitlement_state(request.tenant),
            }
        )


class AccountsView(APIView):
    """L'écran « Équipe » : le client gère les comptes de son espace."""

    permissions = {"get": "accounts.view", "post": "accounts.manage"}

    def get(self, request):
        comptes = (
            Account.objects.for_tenant(request.tenant)
            .select_related("role", "user")
            .order_by("display_name")
        )
        roles = Role.objects.for_tenant(request.tenant).order_by("label")
        return Response(
            {
                "accounts": [serialize_account(a) for a in comptes],
                "roles": [{"key": r.key, "label": r.label} for r in roles],
            }
        )

    def post(self, request):
        try:
            account = create_account(
                request.tenant,
                name=request.data.get("name"),
                username=request.data.get("username"),
                email=request.data.get("email"),
                password=str(request.data.get("password", "")),
                role=str(request.data.get("role", "")).strip() or None,
            )
        except AccountError as exc:
            return refus(exc)
        record("account.created", tenant=request.tenant, actor=actor_of(request), target=account,
               role=account.role.key)
        return Response(serialize_account(account), status=status.HTTP_201_CREATED)


class AccountView(APIView):
    permissions = {"patch": "accounts.manage"}

    def patch(self, request, pk):
        # L'espace fait partie du filtre, pas seulement l'identifiant : sans
        # lui, connaître un id suffirait à toucher le compte d'un autre.
        account = Account.objects.for_tenant(request.tenant).filter(pk=pk).first()
        if account is None:
            return Response({"detail": "Compte introuvable."}, status=status.HTTP_404_NOT_FOUND)
        try:
            changed = update_account(
                account,
                password=str(request.data.get("password", "")) or None,
                role=str(request.data.get("role", "")).strip() or None,
                status=str(request.data.get("status", "")).strip() or None,
                name=str(request.data.get("name", "")).strip() or None,
            )
        except AccountError as exc:
            return refus(exc)
        record("account.updated", tenant=request.tenant, actor=actor_of(request), target=account,
               changed=changed)
        account.refresh_from_db()
        return Response(serialize_account(account))
