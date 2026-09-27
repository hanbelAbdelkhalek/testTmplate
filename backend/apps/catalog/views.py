from rest_framework import serializers

from apps.audit.services import actor_of, record
from apps.entitlements.services import check_limit
from apps.tenancy.views import TenantScopedViewSet

from .models import Item


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        # Jamais `tenant` : l'espace vient de la requête, pas du client.
        fields = ["id", "sku", "name", "price", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_sku(self, value):
        value = value.strip().upper()
        tenant = self.context["request"].tenant
        existe = Item.objects.for_tenant(tenant).filter(sku=value)
        if self.instance:
            existe = existe.exclude(pk=self.instance.pk)
        # Cherché dans l'espace seulement : une référence prise chez un autre
        # client n'est pas prise ici.
        if existe.exists():
            raise serializers.ValidationError("Cette référence existe déjà.")
        return value


class ItemViewSet(TenantScopedViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    module = "catalog"
    permissions = {
        "list": "catalog.view",
        "retrieve": "catalog.view",
        "*": "catalog.manage",
    }

    def perform_create(self, serializer):
        check_limit(
            self.request.tenant, "catalog", "max_items",
            used=Item.objects.for_tenant(self.request.tenant).count(),
        )
        super().perform_create(serializer)
        record("catalog.item_created", tenant=self.request.tenant,
               actor=actor_of(self.request), target=serializer.instance)
