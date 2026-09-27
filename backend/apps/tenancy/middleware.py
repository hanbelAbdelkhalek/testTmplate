from django.conf import settings
from django.http import JsonResponse

from .models import Domain, Tenant, normalize_host

# Routes servies sans espace : santé et version (sondées par Docker et la
# plateforme), et les API de la plateforme, où l'espace est désigné dans
# l'appel, signé.
EXEMPT_PREFIXES = ("/api/health/", "/api/version/", "/api/internal/", "/api/platform/")


def resolve_tenant(request):
    """L'espace visé par la requête, ou None.

    Le frontend appelle Django par son alias interne ; le nom public que le
    client a tapé arrive dans X-Forwarded-Host, posé par le frontend lui-même
    (jamais recopié de ce qu'envoie le navigateur). Django n'étant pas exposé,
    personne d'autre ne peut le poser.
    """
    host = normalize_host(
        request.META.get("HTTP_X_FORWARDED_HOST") or request.META.get("HTTP_HOST", "")
    )
    domain = Domain.objects.select_related("tenant").filter(hostname=host).first()
    if domain:
        return domain.tenant
    if settings.DEFAULT_TENANT_SLUG and host in {"localhost", "127.0.0.1"}:
        return Tenant.objects.filter(slug=settings.DEFAULT_TENANT_SLUG).first()
    return None


class TenantMiddleware:
    """Pose `request.tenant` et refuse tout ce qui n'a pas d'espace valide.

    Étapes 1 et 2 de l'ordre d'évaluation : résoudre l'espace depuis l'hôte,
    puis vérifier qu'il est actif. Les suivantes (module, limite, rôle) sont
    dans apps/rbac/permissions.py.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        if request.path.startswith(EXEMPT_PREFIXES):
            return self.get_response(request)

        tenant = resolve_tenant(request)
        if tenant is None:
            return JsonResponse(
                {"detail": "Espace introuvable.", "code": "tenant_not_found"}, status=404
            )
        if not tenant.is_active:
            return JsonResponse(
                {"detail": "Cet espace est suspendu.", "code": "tenant_suspended"}, status=403
            )
        request.tenant = tenant
        return self.get_response(request)
