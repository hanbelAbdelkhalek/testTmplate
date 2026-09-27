from rest_framework.throttling import SimpleRateThrottle


class LoginThrottle(SimpleRateThrottle):
    """Plafonne les essais de mot de passe par compte visé.

    Par compte et non par adresse IP : derrière le frontend, toutes les
    requêtes arrivent de la même adresse, celle de son conteneur. Le cache
    par défaut est propre à chaque processus ; pour un plafond exact sur
    plusieurs workers, configurer un cache partagé (CACHES).
    """

    scope = "login"

    def get_cache_key(self, request, view):
        username = str(request.data.get("username", "")).strip().lower()
        tenant = getattr(request, "tenant", None)
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{getattr(tenant, 'pk', '-')}:{username}",
        }
