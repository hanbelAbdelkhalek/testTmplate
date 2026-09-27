from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.catalog.views import ItemViewSet
from apps.core.views import LiveView, ReadyView, VersionView
from apps.identity import views as identity
from apps.provisioning import platform_views as platform
from apps.provisioning import views as internal

# Routes métier. Un nouveau module ajoute ici son ViewSet.
router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("catalog/items", ItemViewSet, basename="catalog-item")

internal_patterns = [
    path("tenants/provision/", internal.ProvisionView.as_view()),
    path("tenants/<uuid:external_id>/", internal.TenantView.as_view()),
    path("tenants/<uuid:external_id>/entitlements/", internal.EntitlementsView.as_view()),
    path("tenants/<uuid:external_id>/bootstrap-admin/", internal.BootstrapAdminView.as_view()),
    path("tenants/<uuid:external_id>/accounts/", internal.PlatformAccountsView.as_view()),
    path("tenants/<uuid:external_id>/accounts/<int:pk>/", internal.PlatformAccountView.as_view()),
    path("tenants/<uuid:external_id>/demo-reset/", internal.DemoResetView.as_view()),
    path("jobs/<uuid:job_id>/", internal.JobView.as_view()),
]

# Écrans de la plateforme (comptes et rôles), même forme que l'ERP et Lumina.
platform_patterns = [
    path("tenant-status/", platform.TenantStatusView.as_view()),
    path("bootstrap-admin/", platform.BootstrapAdminView.as_view()),
    path("accounts/", platform.AccountsView.as_view()),
    path("accounts/<int:pk>/", platform.AccountView.as_view()),
    path("roles/", platform.RolesView.as_view()),
    path("roles/<slug:key>/", platform.RoleView.as_view()),
]

urlpatterns = [
    # Sondes : Docker, déploiement, plateforme.
    path("api/health/live/", LiveView.as_view()),
    path("api/health/ready/", ReadyView.as_view()),
    path("api/version/", VersionView.as_view()),
    # Session.
    path("api/auth/login/", identity.LoginView.as_view()),
    path("api/auth/refresh/", identity.RefreshView.as_view()),
    path("api/auth/me/", identity.MeView.as_view()),
    # Comptes de l'espace, gérés par le client.
    path("api/accounts/", identity.AccountsView.as_view()),
    path("api/accounts/<int:pk>/", identity.AccountView.as_view()),
    # Métier.
    path("api/", include(router.urls)),
    # Plateforme SigmaGravity, signé.
    path("api/internal/v1/", include(internal_patterns)),
    path("api/platform/", include(platform_patterns)),
]
