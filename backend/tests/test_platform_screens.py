"""Comptes et rôles gérés depuis les écrans de la plateforme (routes api/platform/)."""

from apps.identity.models import Account
from apps.rbac.models import Role
from apps.tenancy.models import Domain, Tenant

from .helpers import PASSWORD, SolutionTestCase

ADMIN = {"tenant": "dev-client1", "name": "Karim Admin", "username": "karim",
         "email": "karim@client1.test", "password": PASSWORD}


class PlatformScreensTests(SolutionTestCase):
    def bootstrap(self, **extra):
        return self.platform("post", "/api/platform/bootstrap-admin/", {**ADMIN, **extra})

    def test_first_admin_creates_the_space_and_can_log_in(self):
        self.assertEqual(self.platform("get", "/api/platform/tenant-status/?tenant=dev-client1").json(),
                         {"has_admin": False})
        response = self.bootstrap()
        self.assertEqual(response.status_code, 201, response.content)
        tenant = Tenant.objects.get(slug="dev-client1")
        self.assertEqual(Domain.objects.get(tenant=tenant).hostname, "dev-client1.sigmagravity.com")
        self.assertEqual(response.json()["user"]["role"], "admin")
        self.assertEqual(self.bootstrap(username="autre").status_code, 409)
        self.login(tenant, "karim")

    def test_unsigned_calls_are_refused(self):
        self.assertEqual(self.client.get("/api/platform/accounts/?tenant=dev-client1").status_code, 401)

    def test_accounts_in_the_erp_shape(self):
        self.bootstrap()
        created = self.platform("post", "/api/platform/accounts/", {
            "tenant": "dev-client1", "name": "Nadia", "username": "nadia", "email": "n@c.test",
            "password": PASSWORD, "role": "manager"})
        self.assertEqual(created.status_code, 201, created.content)
        listing = self.platform("get", "/api/platform/accounts/?tenant=dev-client1").json()
        self.assertEqual({a["username"] for a in listing["accounts"]}, {"karim", "nadia"})
        self.assertEqual({a["status"] for a in listing["accounts"]}, {"actif"})
        self.assertIn({"value": "admin", "label": "Administrateur", "description": "Toutes les permissions"},
                      listing["roles"])
        patched = self.platform("patch", f"/api/platform/accounts/{created.json()['id']}/",
                                {"tenant": "dev-client1", "status": "inactif"})
        self.assertEqual(patched.json()["status"], "inactif")
        other = self.platform("patch", f"/api/platform/accounts/{created.json()['id']}/",
                              {"tenant": "autre-espace", "status": "actif"})
        self.assertEqual(other.status_code, 404)

    def test_roles_can_be_created_edited_and_deleted(self):
        self.bootstrap()
        catalogue = self.platform("get", "/api/platform/roles/?tenant=dev-client1").json()
        keys = {p["key"] for p in catalogue["permissions"]}
        self.assertTrue({"*", "accounts.manage", "catalog.view", "catalog.*"} <= keys)

        created = self.platform("post", "/api/platform/roles/", {
            "tenant": "dev-client1", "key": "caissier", "label": "Caissier", "permissions": ["catalog.view"]})
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(self.platform("post", "/api/platform/roles/", {
            "tenant": "dev-client1", "key": "x", "label": "X", "permissions": ["inventee.tout"]}).status_code, 400)

        edited = self.platform("patch", "/api/platform/roles/caissier/", {
            "tenant": "dev-client1", "permissions": ["catalog.view", "catalog.manage"]})
        self.assertEqual(edited.json()["permissions"], ["catalog.manage", "catalog.view"])

        # Le compte avec ce rôle en reçoit aussitôt les droits.
        tenant = Tenant.objects.get(slug="dev-client1")
        self.platform("post", "/api/platform/accounts/", {
            "tenant": "dev-client1", "name": "Sara", "username": "sara", "email": "s@c.test",
            "password": PASSWORD, "role": "caissier"})
        token = self.login(tenant, "sara")["access"]
        me = self.api("get", "/api/auth/me/", host="dev-client1.sigmagravity.com", token=token).json()
        self.assertIn("catalog.manage", me["permissions"])

        in_use = self.platform("delete", "/api/platform/roles/caissier/?tenant=dev-client1")
        self.assertEqual(in_use.status_code, 409)
        system = self.platform("delete", "/api/platform/roles/member/?tenant=dev-client1")
        self.assertEqual(system.status_code, 409)
        self.platform("post", "/api/platform/roles/", {
            "tenant": "dev-client1", "key": "vide", "label": "Vide", "permissions": []})
        self.assertEqual(self.platform("delete", "/api/platform/roles/vide/?tenant=dev-client1").status_code, 204)
        self.assertFalse(Role.objects.filter(key="vide").exists())

    def test_last_manager_cannot_lose_account_management(self):
        self.bootstrap()
        response = self.platform("patch", "/api/platform/roles/admin/", {
            "tenant": "dev-client1", "permissions": ["catalog.view"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Role.objects.get(key="admin").permissions, ["*"])
        self.assertEqual(Account.objects.count(), 1)
