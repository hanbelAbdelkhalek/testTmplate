from rest_framework import viewsets


class TenantScopedViewSet(viewsets.ModelViewSet):
    """Base des vues métier : lit et écrit dans l'espace de la requête, nulle part ailleurs.

    Déclarer sur la sous-classe :
        module = "catalog"                      # module d'abonnement requis
        permissions = {"list": "catalog.view",  # permission par action
                       "retrieve": "catalog.view",
                       "*": "catalog.manage"}   # toutes les autres actions

    Le filtrage se fait ici, côté serveur, quelle que soit la requête : un
    identifiant d'un autre espace donne 404, comme s'il n'existait pas.
    """

    def get_queryset(self):
        return super().get_queryset().for_tenant(self.request.tenant)

    def perform_create(self, serializer):
        # L'espace n'est jamais lu dans le corps de la requête : sinon un
        # client écrirait chez un autre en le nommant.
        serializer.save(tenant=self.request.tenant)
