import json
import time
import uuid

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.entitlements.services import ensure_default_modules
from apps.identity.services import create_account
from apps.provisioning.signing import canonical_request, sign
from apps.rbac.services import ensure_default_roles
from apps.tenancy.models import Domain, Tenant

SECRET = "secret-de-test-partage-avec-la-plateforme"
PASSWORD = "Mot-de-passe-de-test-7391"


def make_tenant(slug: str, *, host: str | None = None, is_demo: bool = False) -> Tenant:
    tenant = Tenant.objects.create(slug=slug, display_name=slug.title(), is_demo=is_demo)
    Domain.objects.create(tenant=tenant, hostname=host or f"{slug}.example.test", is_primary=True)
    ensure_default_roles(tenant)
    ensure_default_modules(tenant)
    return tenant


def make_account(tenant, username="admin", role="admin"):
    return create_account(
        tenant, name=username.title(), username=username,
        email=f"{username}@{tenant.slug}.example.test", password=PASSWORD, role=role,
    )


def signed_headers(method, path, body=b"", *, secret=SECRET, key_id="platform-v1",
                   timestamp=None, nonce=None, idempotency_key=None):
    timestamp = str(timestamp if timestamp is not None else int(time.time()))
    nonce = nonce or str(uuid.uuid4())
    canonical = canonical_request(method, path, timestamp, nonce, body)
    return {
        "X-Platform-Key-Id": key_id,
        "X-Platform-Timestamp": timestamp,
        "X-Platform-Nonce": nonce,
        "X-Platform-Signature": sign(secret, canonical),
        "Idempotency-Key": idempotency_key or str(uuid.uuid4()),
    }


@override_settings(PLATFORM_SHARED_SECRET=SECRET, PLATFORM_KEY_ID="platform-v1",
                   SOLUTION_KEY="template", ENVIRONMENT="dev")
class SolutionTestCase(TestCase):
    """Client HTTP qui parle comme le frontend (X-Forwarded-Host) ou comme la plateforme (signé)."""

    def setUp(self):
        # Le plafond de connexions vit dans le cache : sans ce nettoyage, les
        # essais d'un test compteraient dans le suivant.
        cache.clear()

    def host(self, tenant) -> str:
        return tenant.domains.first().hostname

    def api(self, method, path, tenant=None, *, token=None, data=None, host=None):
        headers = {}
        if tenant is not None or host:
            headers["X-Forwarded-Host"] = host or self.host(tenant)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        kwargs = {"headers": headers}
        if data is not None:
            kwargs.update(data=json.dumps(data), content_type="application/json")
        return getattr(self.client, method)(path, **kwargs)

    def login(self, tenant, username="admin", password=PASSWORD) -> dict:
        response = self.api("post", "/api/auth/login/", tenant,
                            data={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def platform(self, method, path, payload=None, **sign_kwargs):
        body = json.dumps(payload).encode() if payload is not None else b""
        headers = signed_headers(method.upper(), path, body, **sign_kwargs)
        kwargs = {"headers": headers}
        if payload is not None:
            kwargs.update(data=body, content_type="application/json")
        return getattr(self.client, method)(path, **kwargs)
