"""
CE QUE LA SOLUTION VEND ET QUI PEUT QUOI.

Le seul fichier du socle à adapter pour chaque solution. Il déclare :

- MODULES     : ce que l'administrateur de la plateforme ouvre ou ferme pour un
                client (droit d'abonnement), avec leurs limites ;
- PERMISSIONS : ce qu'un compte peut faire dans un module ouvert ;
- ROLES       : les rôles posés dans chaque nouvel espace, avec leurs droits ;
- seed_demo() : les données d'un espace de démonstration.

Garder `solution.yaml`, à la racine du dépôt, aligné sur MODULES et ROLES :
c'est ce fichier que la plateforme enregistre.

Les quatre notions à ne pas confondre :
  droit d'abonnement (MODULES)  ce que l'entreprise a acheté
  permission de rôle (ROLES)    ce qu'un membre peut faire dans un module ouvert
  limite (MODULES.limits)       combien il peut en consommer
  affichage (frontend)          une conséquence, jamais une protection
"""

from decimal import Decimal

# Clé → description. `default_enabled` s'applique à un espace créé sans liste
# de modules ; `limits` donne la valeur par défaut de chaque plafond
# (None = illimité).
MODULES: dict[str, dict] = {
    "catalog": {
        "label": "Catalogue",
        "description": "Articles, références et prix.",
        "default_enabled": True,
        "dependencies": [],
        "limits": {"max_items": None},
    },
}

# Permissions hors module : elles existent dans tout espace, quel que soit
# l'abonnement. La gestion des comptes en fait partie — un client qui ne
# pourrait plus gérer ses accès serait bloqué hors de chez lui.
CORE_PERMISSIONS: dict[str, str] = {
    "accounts.view": "Voir les comptes de l'espace",
    "accounts.manage": "Créer, modifier et désactiver des comptes",
    "settings.manage": "Modifier les réglages de l'espace",
}

# Permissions de module : le préfixe avant le point est la clé du module. Un
# module fermé les rend inopérantes, même pour un administrateur.
MODULE_PERMISSIONS: dict[str, str] = {
    "catalog.view": "Consulter le catalogue",
    "catalog.manage": "Ajouter, modifier et supprimer des articles",
}

PERMISSIONS = {**CORE_PERMISSIONS, **MODULE_PERMISSIONS}

# Posés à la création de chaque espace. Un espace sans rôles s'ouvrirait sur
# une coquille vide : le contrôle d'accès refuserait tout, même à
# l'administrateur, et le client croirait le produit cassé.
#
# "*" = toutes les permissions. "catalog.*" = toutes celles du module.
ROLES: dict[str, dict] = {
    "admin": {"label": "Administrateur", "permissions": ["*"]},
    "manager": {
        "label": "Responsable",
        "permissions": ["accounts.view", "catalog.*"],
    },
    "member": {"label": "Membre", "permissions": ["catalog.view"]},
}

# Rôle donné au premier compte d'un espace. Il doit avoir "*" : c'est lui qui
# ouvrira les autres accès.
OWNER_ROLE = "admin"
# Rôle par défaut d'un compte créé sans rôle précisé.
DEFAULT_ROLE = "member"


def seed_demo(tenant) -> dict:
    """Remplit un espace de démonstration. Appelé à la création d'un espace
    `is_demo` et à chaque réinitialisation.

    Ne créer que des lignes rattachées à `tenant`. Renvoie un résumé, écrit
    dans le journal.
    """
    from apps.catalog.models import Item

    articles = [
        ("DEMO-001", "Article de démonstration", Decimal("99.00")),
        ("DEMO-002", "Deuxième article", Decimal("149.50")),
        ("DEMO-003", "Troisième article", Decimal("12.00")),
    ]
    for sku, name, price in articles:
        Item.objects.create(tenant=tenant, sku=sku, name=name, price=price)
    return {"items": len(articles)}
