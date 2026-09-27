from apps.catalog.models import Item
from apps.entitlements.models import TenantModule

from .helpers import SolutionTestCase, make_account, make_tenant


class PermissionTests(SolutionTestCase):
    def setUp(self):
        super().setUp()
        self.t = make_tenant("gamma")
        make_account(self.t, "admin", "admin")
        make_account(self.t, "lecteur", "member")
        self.admin = self.login(self.t, "admin")["access"]
        self.member = self.login(self.t, "lecteur")["access"]

    def test_member_reads_but_cannot_write(self):
        self.assertEqual(self.api("get", "/api/catalog/items/", self.t, token=self.member).status_code, 200)
        response = self.api("post", "/api/catalog/items/", self.t, token=self.member,
                            data={"sku": "X", "name": "X"})
        self.assertEqual(response.status_code, 403)

    def test_member_cannot_manage_accounts(self):
        self.assertEqual(self.api("get", "/api/accounts/", self.t, token=self.member).status_code, 403)

    def test_closed_module_refuses_even_an_admin(self):
        TenantModule.objects.filter(tenant=self.t, key="catalog").update(enabled=False)
        response = self.api("get", "/api/catalog/items/", self.t, token=self.admin)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "module_closed")
        me = self.api("get", "/api/auth/me/", self.t, token=self.admin).json()
        catalog = next(m for m in me["entitlements"]["modules"] if m["key"] == "catalog")
        self.assertFalse(catalog["enabled"])

    def test_limit_blocks_creation_without_deleting(self):
        TenantModule.objects.filter(tenant=self.t, key="catalog").update(limits={"max_items": 1})
        Item.objects.create(tenant=self.t, sku="A", name="A")
        response = self.api("post", "/api/catalog/items/", self.t, token=self.admin,
                            data={"sku": "B", "name": "B"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "limit_reached")
        self.assertEqual(Item.objects.filter(tenant=self.t).count(), 1)

    def test_anonymous_is_refused(self):
        self.assertIn(self.api("get", "/api/catalog/items/", self.t).status_code, (401, 403))

    def test_health_and_version_need_no_space(self):
        for path in ("/api/health/live/", "/api/health/ready/", "/api/version/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/api/version/").json()["solution"], "template")
