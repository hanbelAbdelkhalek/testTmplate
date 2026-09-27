from .models import AuditEvent


def actor_of(request) -> str:
    """Qui agit : un compte de l'espace, ou la plateforme (appel signé)."""
    key_id = getattr(request, "platform_key_id", None)
    if key_id:
        return f"platform:{key_id}"
    account = getattr(getattr(request, "user", None), "account", None)
    return f"account:{account.pk}" if account else "anonymous"


def record(action: str, *, tenant=None, actor: str = "system", target=None, **metadata) -> AuditEvent:
    """Écrit un événement. `metadata` ne doit contenir ni mot de passe ni secret."""
    return AuditEvent.objects.create(
        tenant_id=getattr(tenant, "pk", tenant),
        actor=actor,
        action=action,
        target_type=type(target).__name__.lower() if target is not None else "",
        target_id=str(getattr(target, "pk", "")) if target is not None else "",
        metadata=metadata,
    )
