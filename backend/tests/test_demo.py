"""L'espace de démonstration : référence enregistrée, retour à la référence."""

from apps.catalog.models import Item
from apps.identity.models import Account
from apps.tenancy.models import Tenant

from .helpers import PASSWORD, SolutionTestCase, make_account, make_tenant

AUTRE = "Autre-mot-de-passe-5521"


class DemoTests(SolutionTestCase):
    def ouvrir(self, tenant="dev-demo-crm"):
        return self.platform("post", "/api/platform/demo/", {"tenant": tenant, "company": "Démo CRM"})

    def test_open_creates_a_demo_space_with_sample_data(self):
        response = self.ouvrir()
        self.assertEqual(response.status_code, 201, response.content)
        tenant = Tenant.objects.get(slug="dev-demo-crm")
        self.assertTrue(tenant.is_demo)
        self.assertEqual(Item.objects.filter(tenant=tenant).count(), 3)
        self.assertIsNone(response.json()["snapshot_at"])
        # Rouvrir ne recrée rien.
        self.assertEqual(self.ouvrir().status_code, 200)
        self.assertEqual(Item.objects.filter(tenant=tenant).count(), 3)

    def test_a_real_space_never_becomes_a_demo(self):
        vrai = make_tenant("vrai-client")
        make_account(vrai)
        response = self.ouvrir("vrai-client")
        self.assertEqual(response.status_code, 409)
        vrai.refresh_from_db()
        self.assertFalse(vrai.is_demo)

    def test_reset_returns_exactly_to_the_reference(self):
        self.ouvrir()
        tenant = Tenant.objects.get(slug="dev-demo-crm")
        self.platform("post", "/api/platform/bootstrap-admin/", {
            "tenant": "dev-demo-crm", "name": "Démo", "username": "demo", "email": "demo@demo.test",
            "password": PASSWORD})
        Item.objects.create(tenant=tenant, sku="REF-ADMIN", name="Saisi par l'administrateur")
        self.assertEqual(self.platform("post", "/api/platform/demo/snapshot/", {"tenant": "dev-demo-crm"}).status_code, 200)
        reference = sorted(Item.objects.filter(tenant=tenant).values_list("sku", "name"))

        # Un visiteur passe : il ajoute, modifie, supprime, crée un compte, change le mot de passe.
        autre = make_tenant("autre-espace")
        Item.objects.create(tenant=autre, sku="AILLEURS", name="Ne pas toucher")
        Item.objects.create(tenant=tenant, sku="VISITEUR", name="Ajouté par un visiteur")
        Item.objects.filter(tenant=tenant, sku="DEMO-001").update(name="Modifié par un visiteur")
        Item.objects.filter(tenant=tenant, sku="DEMO-002").delete()
        make_account(tenant, "visiteur", "member")
        compte = Account.objects.get(tenant=tenant, username="demo")
        compte.user.set_password(AUTRE)
        compte.user.save()

        response = self.platform("post", "/api/platform/demo/reset/", {"tenant": "dev-demo-crm"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(sorted(Item.objects.filter(tenant=tenant).values_list("sku", "name")), reference)
        self.assertEqual(list(Account.objects.filter(tenant=tenant).values_list("username", flat=True)), ["demo"])
        self.login(tenant, "demo", PASSWORD)  # le mot de passe de la référence
        self.assertTrue(Item.objects.filter(tenant=autre, sku="AILLEURS").exists())

    def test_reset_is_refused_without_reference_or_outside_a_demo(self):
        self.ouvrir()
        self.assertEqual(self.platform("post", "/api/platform/demo/reset/", {"tenant": "dev-demo-crm"}).json()["code"],
                         "no_snapshot")
        make_tenant("client-reel")
        self.assertEqual(self.platform("post", "/api/platform/demo/reset/", {"tenant": "client-reel"}).json()["code"],
                         "not_demo")
