"""
Vérification des appels signés de la plateforme (HMAC-SHA256).

Même calcul que nfc/backend/apps/tenants/solution_client.py, côté plateforme :

    canonique = MÉTHODE \\n chemin?requête \\n horodatage \\n nonce \\n sha256(corps)
    signature = HMAC-SHA256(PLATFORM_SHARED_SECRET, canonique), en hexadécimal

En-têtes attendus : X-Platform-Key-Id, X-Platform-Timestamp, X-Platform-Nonce,
X-Platform-Signature, Idempotency-Key.
"""

import hashlib
import hmac
import time
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from .models import UsedNonce


class SignatureError(Exception):
    code = "signature_invalid"


class SignatureNotConfigured(SignatureError):
    code = "signature_not_configured"


class StaleSignature(SignatureError):
    code = "signature_stale"


class ReplayedSignature(SignatureError):
    code = "signature_replayed"


def canonical_request(method: str, path_with_query: str, timestamp: str, nonce: str, body: bytes) -> str:
    return "\n".join(
        [method.upper(), path_with_query, timestamp, nonce, hashlib.sha256(body).hexdigest()]
    )


def sign(secret: str, canonical: str) -> str:
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def verify(request) -> str:
    """Vérifie l'appel ; renvoie l'identifiant de clé. Lève SignatureError sinon.

    Ordre voulu : tout ce qui ne coûte rien (en-têtes, clé, fraîcheur,
    signature) avant d'écrire le nonce en base.
    """
    secret = settings.PLATFORM_SHARED_SECRET
    if not secret:
        # Sans secret, refuser : ouvrir ces routes rendrait publique la
        # création de comptes administrateur.
        raise SignatureNotConfigured("PLATFORM_SHARED_SECRET absent")

    headers = request.headers
    key_id = headers.get("X-Platform-Key-Id", "")
    timestamp = headers.get("X-Platform-Timestamp", "")
    nonce = headers.get("X-Platform-Nonce", "")
    signature = headers.get("X-Platform-Signature", "")
    if not all((key_id, timestamp, nonce, signature, headers.get("Idempotency-Key"))):
        raise SignatureError("en-têtes signés manquants")
    if not hmac.compare_digest(key_id, settings.PLATFORM_KEY_ID):
        raise SignatureError("clé inconnue")

    try:
        horodatage = int(timestamp)
    except ValueError as exc:
        raise SignatureError("horodatage illisible") from exc
    tolerance = settings.PLATFORM_SIGNATURE_TOLERANCE_SECONDS
    if abs(int(time.time()) - horodatage) > tolerance:
        raise StaleSignature("appel trop ancien ou daté du futur")

    canonical = canonical_request(
        request.method, request.get_full_path(), timestamp, nonce, request.body
    )
    if not hmac.compare_digest(sign(secret, canonical), signature):
        raise SignatureError("signature invalide")

    try:
        UsedNonce.objects.create(key_id=key_id, nonce=nonce)
    except IntegrityError as exc:
        raise ReplayedSignature("nonce déjà utilisé") from exc
    # Au-delà de deux fois la fenêtre, un nonce ne peut plus servir : l'appel
    # serait refusé comme trop ancien. On l'oublie.
    UsedNonce.objects.filter(created_at__lt=timezone.now() - timedelta(seconds=tolerance * 2)).delete()
    return key_id
