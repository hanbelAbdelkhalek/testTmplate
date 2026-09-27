from apps.core import solution

from .models import Role


def ensure_default_roles(tenant) -> list[Role]:
    """Pose les rôles de solution.ROLES qui manquent. Sans effet s'ils existent.

    Appelé à la création d'un espace, et de nouveau à chaque provisionnement :
    un rôle ajouté plus tard dans solution.py arrive ainsi dans les espaces
    déjà ouverts. Les droits d'un rôle existant ne sont pas écrasés — le
    client a pu les ajuster.
    """
    roles = []
    for key, spec in solution.ROLES.items():
        role, _ = Role.objects.get_or_create(
            tenant=tenant,
            key=key,
            defaults={
                "label": spec["label"],
                "permissions": list(spec["permissions"]),
                "is_system": True,
            },
        )
        roles.append(role)
    return roles
