"""L'API interne, telle que la plateforme l'appelle."""

import time
import uuid

from django.test import override_settings

from apps.catalog.models import Item
from apps.entitlements.models import TenantModule
from apps.identity.models import Account
from apps.rbac.models import Role
from apps.tenancy.models import Domain, Tenant

from .helpers import PASSWORD, SolutionTestCase, make_tenant

PROVISION = "/api/internal/v1/tenants/provision/"


def provision_payload(external_id=None, *, slug="client1", host="client1.example.test",
                      revision=1, modules=None, is_demo=False, solution="template"):
    return {
        "event_id": str(uuid.uuid4()),
        "action": "create_tenant",
        "solution": {"key": solution, "environment": "dev"},
        "tenant": {
            "external_id": str(external_id or uuid.uuid4()),
            "slug": slug,
            "display_name": "Client Un",
            "is_demo": is_demo,
        },
        "owner": {"name": "Karim", "email": "karim@client1.example.test", "username": "karim"},
        "subscription": {
            "plan_key": "standard",
            "revision": revision,
            "modules": modules if modules is not None else [{"key": "catalog", "enabled": True}],
            "limits": {},
        },
        "template": {"key": "standard", "version": "1.0.0"},
        "domains": {"platform_hostname": host, "custom_hostnames": []},
    }


class SignatureTests(SolutionTestCase):
    def test_valid_call_creates_a_ready_space(self):
        response = self.platform("post", PROVISION, provision_payload())
        self.assertEqual(response.status_code, 201, response.content)
        tenant = Tenant.objects.get(slug="client1")
        self.assertEqual(Domain.objects.get(tenant=tenant).hostname, "client1.example.test")
        self.assertEqual(set(Role.objects.filter(tenant=tenant).values_list("key", flat=True)),
                         {"admin", "manager", "member"})
        self.assertTrue(TenantModule.objects.get(tenant=tenant, key="catalog").enabled)
        self.assertEqual(tenant.entitlement_revision, 1)
        self.assertFalse(response.json()["has_admin"])

    def test_wrong_signature_is_refused(self):
        response = self.platform("post", PROVISION, provision_payload(), secret="pas-le-bon")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Tenant.objects.exists())

    def test_stale_timestamp_is_refused(self):
        response = self.platform("post", PROVISION, provision_payload(), timestamp=int(time.time()) - 3600)
        self.assertEqual(response.status_code, 401)

    def test_replayed_nonce_is_refused(self):
        nonce = str(uuid.uuid4())
        payload = provision_payload()
        self.assertEqual(self.platform("post", PROVISION, payload, nonce=nonce).status_code, 201)
        self.assertEqual(self.platform("post", PROVISION, payload, nonce=nonce).status_code, 401)

    def test_unknown_key_id_is_refused(self):
        response = self.platform("post", PROVISION, provision_payload(), key_id="autre-cle")
        self.assertEqual(response.status_code, 401)

    def test_unsigned_browser_call_is_refused(self):
        response = self.client.post(PROVISION, data=b"{}", content_type="application/json")
        self.assertEqual(response.status_code, 401)

    @override_settings(PLATFORM_SHARED_SECRET="")
    def test_no_secret_configured_closes_the_routes(self):
        response = self.platform("post", PROVISION, provision_payload())
        self.assertEqual(response.status_code, 503)


class IdempotencyTests(SolutionTestCase):
    def test_same_key_same_body_replays_the_response(self):
        payload = provision_payload()
        first = self.platform("post", PROVISION, payload, idempotency_key="cle-1")
        second = self.platform("post", PROVISION, payload, idempotency_key="cle-1")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second["Idempotent-Replayed"], "true")
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Tenant.objects.count(), 1)

    def test_same_key_other_body_is_a_conflict(self):
        self.platform("post", PROVISION, provision_payload(), idempotency_key="cle-2")
        response = self.platform("post", PROVISION, provision_payload(slug="autre", host="autre.example.test"),
                                 idempotency_key="cle-2")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "idempotency_conflict")


class ProvisioningTests(SolutionTestCase):
    def setUp(self):
        super().setUp()
        self.external_id = uuid.uuid4()
        self.platform("post", PROVISION, provision_payload(self.external_id))
        self.tenant = Tenant.objects.get(external_id=self.external_id)
        self.base = f"/api/internal/v1/tenants/{self.external_id}/"

    def test_call_for_another_solution_or_stack_is_refused(self):
        response = self.platform("post", PROVISION, provision_payload(solution="erp"))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "wrong_solution")

    def test_invalid_contract_is_refused_with_details(self):
        payload = provision_payload()
        payload["tenant"]["slug"] = "Pas Valide"
        response = self.platform("post", PROVISION, payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "contract_invalid")

    def test_host_of_another_space_is_refused(self):
        response = self.platform("post", PROVISION, provision_payload(slug="intrus"))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "host_taken")

    def test_bootstrap_admin_once_then_login(self):
        body = {"name": "Karim", "username": "karim", "email": "karim@client1.example.test",
                "password": PASSWORD}
        first = self.platform("post", self.base + "bootstrap-admin/", body)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.json()["account"]["role"], "admin")
        again = self.platform("post", self.base + "bootstrap-admin/", {**body, "username": "autre"})
        self.assertEqual(again.status_code, 409)
        tokens = self.login(self.tenant, "karim")
        self.assertTrue(tokens["access"])

    def test_platform_manages_accounts(self):
        self.platform("post", self.base + "bootstrap-admin/", {
            "name": "Karim", "username": "karim", "email": "k@client1.example.test", "password": PASSWORD})
        created = self.platform("post", self.base + "accounts/", {
            "name": "Nadia", "username": "nadia", "email": "n@client1.example.test",
            "password": PASSWORD, "role": "manager"})
        self.assertEqual(created.status_code, 201, created.content)
        listing = self.platform("get", self.base + "accounts/").json()
        self.assertEqual({a["username"] for a in listing["accounts"]}, {"karim", "nadia"})
        self.assertEqual({r["key"] for r in listing["roles"]}, {"admin", "manager", "member"})
        patched = self.platform("patch", self.base + f"accounts/{created.json()['id']}/", {"status": "inactive"})
        self.assertEqual(patched.json()["status"], "inactive")
        karim = Account.objects.get(username="karim")
        last = self.platform("patch", self.base + f"accounts/{karim.pk}/", {"role": "member"})
        self.assertEqual(last.status_code, 409)

    def test_entitlement_revisions_only_move_forward(self):
        def put(revision, enabled):
            return self.platform("put", self.base + "entitlements/", {
                "event_id": str(uuid.uuid4()),
                "action": "update_entitlements",
                "solution": {"key": "template", "environment": "dev"},
                "tenant_external_id": str(self.external_id),
                "subscription": {"plan_key": "pro", "revision": revision,
                                 "modules": [{"key": "catalog", "enabled": enabled}],
                                 "limits": {"catalog": {"max_items": 10}}},
            })

        self.assertEqual(put(3, False).status_code, 200)
        self.assertFalse(TenantModule.objects.get(tenant=self.tenant, key="catalog").enabled)
        older = put(2, True)
        self.assertEqual(older.status_code, 409)
        self.assertEqual(older.json()["code"], "stale_revision")
        self.assertFalse(TenantModule.objects.get(tenant=self.tenant, key="catalog").enabled)
        same = put(3, False)
        self.assertEqual(same.status_code, 200)
        self.assertFalse(same.json()["applied"])
        state = self.platform("get", self.base + "entitlements/").json()
        self.assertEqual(state["revision"], 3)
        self.assertEqual(state["modules"][0]["limits"]["max_items"], 10)

    def test_unknown_module_is_refused(self):
        response = self.platform("post", PROVISION, provision_payload(
            slug="client2", host="client2.example.test",
            modules=[{"key": "inexistant", "enabled": True}]))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Tenant.objects.filter(slug="client2").exists())

    def test_suspend_then_reactivate(self):
        self.assertEqual(self.platform("patch", self.base, {"status": "suspended"}).status_code, 200)
        response = self.api("post", "/api/auth/login/", self.tenant, data={"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 403)
        self.platform("patch", self.base, {"status": "active"})
        response = self.api("post", "/api/auth/login/", self.tenant, data={"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 401)


class DemoResetTests(SolutionTestCase):
    def reset_payload(self, external_id):
        return {
            "event_id": str(uuid.uuid4()),
            "action": "reset_demo",
            "solution": {"key": "template", "environment": "dev"},
            "tenant_external_id": str(external_id),
            "template": {"key": "standard", "version": "1.1.0"},
        }

    def test_demo_is_reset_and_other_spaces_survive(self):
        demo_id = uuid.uuid4()
        self.platform("post", PROVISION, provision_payload(demo_id, slug="demo", host="demo.example.test",
                                                           is_demo=True))
        demo = Tenant.objects.get(slug="demo")
        self.assertEqual(Item.objects.filter(tenant=demo).count(), 3)
        Item.objects.create(tenant=demo, sku="AJOUT", name="Ajouté pendant la démo")
        client = make_tenant("vrai-client")
        Item.objects.create(tenant=client, sku="GARDE", name="À garder")

        response = self.platform("post", f"/api/internal/v1/tenants/{demo_id}/demo-reset/",
                                 self.reset_payload(demo_id))
        self.assertEqual(response.status_code, 202, response.content)
        job = self.platform("get", f"/api/internal/v1/jobs/{response.json()['id']}/").json()
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(Item.objects.filter(tenant=demo).count(), 3)
        self.assertFalse(Item.objects.filter(tenant=demo, sku="AJOUT").exists())
        self.assertTrue(Item.objects.filter(tenant=client, sku="GARDE").exists())
        self.assertTrue(Role.objects.filter(tenant=demo).exists())

    def test_real_space_cannot_be_reset(self):
        external_id = uuid.uuid4()
        self.platform("post", PROVISION, provision_payload(external_id))
        tenant = Tenant.objects.get(external_id=external_id)
        Item.objects.create(tenant=tenant, sku="VRAI", name="Donnée réelle")
        response = self.platform("post", f"/api/internal/v1/tenants/{external_id}/demo-reset/",
                                 self.reset_payload(external_id))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Item.objects.filter(tenant=tenant, sku="VRAI").exists())
