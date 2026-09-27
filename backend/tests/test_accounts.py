from apps.audit.models import AuditEvent
from apps.identity.models import Account

from .helpers import PASSWORD, SolutionTestCase, make_account, make_tenant

NEW_PASSWORD = "Autre-mot-de-passe-4410"


class AccountTests(SolutionTestCase):
    def setUp(self):
        super().setUp()
        self.t = make_tenant("delta")
        self.owner = make_account(self.t, "admin", "admin")
        self.tokens = self.login(self.t)

    def create(self, **data):
        payload = {"name": "Sara", "username": "sara", "email": "sara@delta.example.test",
                   "password": PASSWORD, "role": "member", **data}
        return self.api("post", "/api/accounts/", self.t, token=self.tokens["access"], data=payload)

    def test_admin_creates_account_that_can_log_in(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotIn("password", response.json())
        self.login(self.t, "sara")

    def test_username_unique_within_space(self):
        self.create()
        self.assertEqual(self.create().status_code, 409)

    def test_weak_password_refused(self):
        response = self.create(password="123")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Account.objects.filter(username="sara").exists())

    def test_last_admin_cannot_be_demoted_or_disabled(self):
        path = f"/api/accounts/{self.owner.pk}/"
        for change in ({"role": "member"}, {"status": "inactive"}):
            response = self.api("patch", path, self.t, token=self.tokens["access"], data=change)
            self.assertEqual(response.status_code, 409, change)
            self.assertEqual(response.json()["code"], "last_admin")

    def test_password_change_ends_existing_sessions(self):
        sara = self.create().json()
        old = self.login(self.t, "sara")
        response = self.api("patch", f"/api/accounts/{sara['id']}/", self.t,
                            token=self.tokens["access"], data={"password": NEW_PASSWORD})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.api("get", "/api/auth/me/", self.t, token=old["access"]).status_code, 401
        )
        refresh = self.api("post", "/api/auth/refresh/", self.t, data={"refresh": old["refresh"]})
        self.assertEqual(refresh.status_code, 401)
        self.login(self.t, "sara", NEW_PASSWORD)

    def test_disabled_account_cannot_log_in(self):
        sara = self.create().json()
        self.api("patch", f"/api/accounts/{sara['id']}/", self.t, token=self.tokens["access"],
                 data={"status": "inactive"})
        response = self.api("post", "/api/auth/login/", self.t,
                            data={"username": "sara", "password": PASSWORD})
        self.assertEqual(response.status_code, 401)

    def test_refresh_gives_a_working_access_token(self):
        response = self.api("post", "/api/auth/refresh/", self.t, data={"refresh": self.tokens["refresh"]})
        self.assertEqual(response.status_code, 200)
        me = self.api("get", "/api/auth/me/", self.t, token=response.json()["access"])
        self.assertEqual(me.status_code, 200)
        self.assertIn("accounts.manage", me.json()["permissions"])

    def test_actions_are_audited_without_secrets(self):
        self.create()
        event = AuditEvent.objects.get(action="account.created")
        self.assertEqual(event.actor, f"account:{self.owner.pk}")
        self.assertNotIn(PASSWORD, str(event.metadata))

    def test_password_guessing_is_throttled_per_account(self):
        for _ in range(20):
            self.api("post", "/api/auth/login/", self.t, data={"username": "admin", "password": "faux"})
        response = self.api("post", "/api/auth/login/", self.t, data={"username": "admin", "password": PASSWORD})
        self.assertEqual(response.status_code, 429)
        # Un autre compte du même espace n'est pas bloqué pour autant.
        other = self.api("post", "/api/auth/login/", self.t, data={"username": "autre", "password": "x"})
        self.assertEqual(other.status_code, 401)
