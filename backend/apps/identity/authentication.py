from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken

# Nom de la revendication qui lie un jeton à son espace.
TENANT_CLAIM = "tid"


def tokens_for(account) -> dict:
    """Jetons d'accès et de renouvellement, liés à l'espace du compte."""
    refresh = RefreshToken.for_user(account.user)
    refresh[TENANT_CLAIM] = account.tenant_id
    # Recopié dans le jeton d'accès par SimpleJWT.
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class TenantJWTAuthentication(JWTAuthentication):
    """Jeton valide ET émis pour l'espace de la requête ET compte actif.

    Sans la vérification d'espace, un compte d'un client pourrait présenter
    son jeton sur l'adresse d'un autre : la signature serait bonne, le
    compte aussi, et le cloisonnement ne tiendrait qu'au filtre des vues.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        tenant = getattr(request._request, "tenant", None)
        if tenant is None or token.get(TENANT_CLAIM) != tenant.pk:
            raise AuthenticationFailed("Jeton émis pour un autre espace.", code="wrong_tenant")
        account = getattr(user, "account", None)
        check_account(account, tenant, token)
        return user, token


def check_account(account, tenant, token) -> None:
    """Refus commun à l'authentification et au renouvellement des jetons."""
    if account is None or account.tenant_id != tenant.pk or not account.is_active:
        raise AuthenticationFailed("Compte désactivé.", code="account_inactive")
    if not account.accepts_token_issued_at(token.get("iat")):
        raise AuthenticationFailed("Session expirée. Reconnectez-vous.", code="token_revoked")
