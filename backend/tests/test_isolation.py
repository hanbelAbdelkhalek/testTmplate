"""Le test qui compte : deux espaces, et l'un ne voit rien de l'autre."""

from apps.catalog.models import Item
from apps.identity.models import Account
from apps.tenancy.models import Tenant

from .helpers import SolutionTestCase, make_account, make_tenant


class IsolationTests(SolutionTestCase):
    def setUp(self):
        super().setUp()
        self.a = make_tenant("alpha")
        self.b = make_tenant("beta")
        make_account(self.a)
        make_account(self.b)
        self.item_a = Item.objects.create(tenant=self.a, sku="REF-001", name="Chez A")
        self.item_b = Item.objects.create(tenant=self.b, sku="REF-001", name="Chez B")
        self.token_a = self.login(self.a)["access"]

    def test_list_shows_only_own_rows(self):
        response = self.api("get", "/api/catalog/items/", self.a, token=self.token_a)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([i["name"] for i in response.json()["results"]], ["Chez A"])

    def test_other_tenant_rows_do_not_exist_for_detail_update_delete(self):
        path = f"/api/catalog/items/{self.item_b.pk}/"
        self.assertEqual(self.api("get", path, self.a, token=self.token_a).status_code, 404)
        self.assertEqual(
            self.api("patch", path, self.a, token=self.token_a, data={"name": "volé"}).status_code, 404
        )
        self.assertEqual(self.api("delete", path, self.a, token=self.token_a).status_code, 404)
        self.item_b.refresh_from_db()
        self.assertEqual(self.item_b.name, "Chez B")

    def test_tenant_in_body_is_ignored(self):
        response = self.api("post", "/api/catalog/items/", self.a, token=self.token_a,
                            data={"sku": "REF-002", "name": "Nouveau", "tenant": self.b.pk})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Item.objects.get(sku="REF-002").tenant, self.a)

    def test_same_reference_allowed_in_two_spaces_but_not_twice_in_one(self):
        response = self.api("post", "/api/catalog/items/", self.a, token=self.token_a,
                            data={"sku": "ref-001", "name": "Doublon"})
        self.assertEqual(response.status_code, 400)

    def test_token_of_one_space_is_refused_on_another(self):
        response = self.api("get", "/api/catalog/items/", self.b, token=self.token_a)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "wrong_tenant")

    def test_credentials_of_one_space_do_not_open_another(self):
        response = self.api("post", "/api/auth/login/", self.b,
                            data={"username": "admin", "password": "wrong-for-b"})
        self.assertEqual(response.status_code, 401)
        # Même identifiant, même mot de passe de test : ce sont deux comptes
        # distincts, et chacun n'ouvre que son espace.
        token_b = self.login(self.b)["access"]
        me = self.api("get", "/api/auth/me/", self.b, token=token_b).json()
        self.assertEqual(me["tenant"]["slug"], "beta")

    def test_unknown_host_reaches_no_code(self):
        response = self.api("get", "/api/catalog/items/", host="inconnu.example.test", token=self.token_a)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "tenant_not_found")

    def test_suspended_space_is_closed(self):
        Tenant.objects.filter(pk=self.a.pk).update(status=Tenant.STATUS_SUSPENDED)
        response = self.api("get", "/api/catalog/items/", self.a, token=self.token_a)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "tenant_suspended")

    def test_accounts_of_other_space_are_invisible(self):
        response = self.api("get", "/api/accounts/", self.a, token=self.token_a)
        emails = [a["email"] for a in response.json()["accounts"]]
        self.assertEqual(emails, ["admin@alpha.example.test"])
        compte_b = Account.objects.get(tenant=self.b)
        response = self.api("patch", f"/api/accounts/{compte_b.pk}/", self.a, token=self.token_a,
                            data={"status": "inactive"})
        self.assertEqual(response.status_code, 404)
