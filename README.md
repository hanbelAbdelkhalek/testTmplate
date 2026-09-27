# Modèle de solution SigmaGravity

Le point de départ de toute nouvelle solution branchée sur la plateforme
SigmaGravity (ERP, boutique, CRM, caisse…). Il contient déjà tout ce qui est
commun à toutes les solutions ; il ne reste à écrire que le métier.

| Déjà fait | Où |
|---|---|
| Espaces clients cloisonnés (un client ne voit jamais les données d'un autre) | `backend/apps/tenancy` |
| Comptes, connexion, mots de passe, dernier administrateur protégé | `backend/apps/identity` |
| Rôles et permissions | `backend/apps/rbac` |
| Modules d'abonnement et limites, ouverts ou fermés par la plateforme | `backend/apps/entitlements` |
| API interne signée pour la plateforme : créer un espace, gérer ses comptes, ses droits, réinitialiser une démo | `backend/apps/provisioning` |
| Journal d'audit | `backend/apps/audit` |
| Module d'exemple complet, à copier puis remplacer | `backend/apps/catalog`, `frontend/src/app/(dashboard)/dashboard/catalogue` |
| Frontend : connexion, tableau de bord, écran « Équipe », menu selon les droits | `frontend/src` |
| Docker ARM64 non-root, Compose sans port publié, déploiement dev/prod | `docker-compose.yml`, `deploy.sh` |
| Tests : isolation, permissions, comptes, appels signés | `backend/tests` |

**Le seul fichier du socle à adapter :** `backend/apps/core/solution.py`
(modules vendus, permissions, rôles par défaut, données de démonstration).

---

## Les commandes

| Pour | Commande |
|---|---|
| Créer une nouvelle solution depuis ce modèle | `scripts/nouvelle-solution.sh crm "SigmaGravity CRM"` |
| Installer les dépendances | `scripts/installer.sh` |
| Ajouter un module métier (backend) | `scripts/nouveau-module.sh ventes` |
| Lancer le backend en local | `scripts/dev-backend.sh` → http://127.0.0.1:8000 |
| Lancer le frontend en local | `scripts/dev-frontend.sh` → http://localhost:3100 |
| Créer un espace de test en local | `cd backend && python manage.py creer_espace demo --host localhost --demo` |
| Tests backend | `cd backend && python manage.py test` |
| Contrôles frontend | `cd frontend && npx eslint src && npm run build` |
| Déployer | `./deploy.sh dev` ou `./deploy.sh prod` (sur le serveur) |

Le squelette a été généré avec les commandes officielles — `django-admin
startproject config .`, `python manage.py startapp <app> apps/<app>`,
`npx create-next-app@latest frontend --ts --tailwind --eslint --app --src-dir`
— puis complété. `nouveau-module.sh` s'appuie sur `startapp --template`.

---

## Comment ça marche

```
navigateur ──► nginx ──► Next.js (frontend) ──► Django (backend) ──► PostgreSQL
                            │   cookies httpOnly     ▲
                            │   X-Forwarded-Host     │ API interne signée (HMAC)
                            └────────────────────────┘
                                       plateforme SigmaGravity ─┘
```

- **Tout passe par Next.** Django n'est pas exposé : Next le joint sur le réseau
  Docker, ajoute le jeton (lu dans un cookie httpOnly que le JavaScript ne peut
  pas lire) et l'adresse visitée (`X-Forwarded-Host`).
- **L'adresse désigne l'espace.** Django cherche le nom d'hôte tel quel dans la
  table `Domain` — pas de découpage de préfixe. Hôte inconnu : 404, avant tout
  code métier. Espace suspendu : 403.
- **Un jeton ne vaut que pour son espace.** Présenté sur l'adresse d'un autre
  client, il est refusé (401), même valide.
- **Chaque vue déclare ce qu'elle exige :**

  ```python
  class ItemViewSet(TenantScopedViewSet):   # filtre et écrit dans l'espace, toujours
      module = "catalog"                    # module d'abonnement : fermé → 403, même pour un admin
      permissions = {"list": "catalog.view", "*": "catalog.manage"}   # action absente → refusée
  ```

## Les comptes

- Un compte appartient à **un** espace. L'identifiant est unique **dans**
  l'espace : deux clients ont chacun leur « admin ».
- **Le premier compte** d'un espace (rôle `admin`) est créé par le client
  depuis la plateforme (`bootstrap-admin`), une seule fois. La plateforme relaie
  son mot de passe sans le stocker.
- Ensuite **le client gère son équipe** dans l'écran « Équipe » (`/dashboard/equipe`),
  et **SigmaGravity peut faire la même chose** depuis la plateforme par l'API
  interne. Les deux passent par les mêmes règles (`apps/identity/services.py`) :
  mot de passe validé, identifiant unique, impossible de retirer le dernier
  compte capable de gérer les accès.
- Changer un mot de passe ou désactiver un compte **coupe ses sessions ouvertes**.
- Essais de mot de passe plafonnés par compte (20 par heure, `LOGIN_RATE`).

## L'API interne (plateforme → solution)

Toutes sous `/api/internal/v1/`, signées HMAC-SHA256 avec
`PLATFORM_SHARED_SECRET`, fenêtre de 5 minutes, nonce à usage unique,
`Idempotency-Key` obligatoire. Contrat identique à
`nfc/backend/apps/tenants/contracts.py` (copié dans `apps/provisioning/contracts.py`).

| Méthode | Chemin | Rôle |
|---|---|---|
| POST | `tenants/provision/` | créer / mettre à jour un espace (rôles, modules, adresses) |
| GET, PATCH | `tenants/<external_id>/` | état ; suspendre, réactiver, renommer |
| GET, PUT | `tenants/<external_id>/entitlements/` | modules, limites, consommation ; appliquer une révision |
| POST | `tenants/<external_id>/bootstrap-admin/` | premier compte administrateur |
| GET, POST | `tenants/<external_id>/accounts/` | comptes et rôles ; ajouter un compte |
| PATCH | `tenants/<external_id>/accounts/<id>/` | mot de passe, rôle, état |
| POST | `tenants/<external_id>/demo-reset/` | réinitialiser un espace de démonstration |
| GET | `jobs/<id>/` | état d'une opération |

Un appel destiné à une autre solution ou à l'autre pile (`solution.key`,
`solution.environment`) est refusé (409) avant d'écrire quoi que ce soit.

---

## Brancher une nouvelle solution

1. **Créer le dépôt** : `scripts/nouvelle-solution.sh <cle> "<Nom>"`, puis le
   pousser sur GitHub avec deux branches, `dev` et `main`.
2. **Écrire le métier** : `backend/apps/core/solution.py` (modules, rôles),
   `scripts/nouveau-module.sh <module>` pour chaque module, les pages dans
   `frontend/src/app/(dashboard)/dashboard/`, le menu dans
   `frontend/src/app/(dashboard)/dashboard/layout.tsx`. Garder `solution.yaml`
   aligné.
3. **Enregistrer dans la plateforme** (écran « Gestion des solutions », sur
   dev.sigmagravity.com puis sigmagravity.com) : dépôt, branche, et **toutes
   les variables** de `.env.example` dans « Variables d'environnement ».
   `SECRET_KEY`, `DATABASE_URL` et `PLATFORM_SHARED_SECRET` en secret.
   Dans « Réglages avancés » : l'URL API interne
   `http://<cle>-dev-backend:8000/api` (c'est elle qui active les appels
   signés).
4. **Première mise en service** sur le serveur, une fois par pile :

   ```bash
   docker exec -it global_postgres psql -U postgres \
     -c "CREATE ROLE <cle>_dev LOGIN PASSWORD '<mot de passe>';" \
     -c "CREATE DATABASE <cle>_dev OWNER <cle>_dev;"
   git clone <dépôt> ~/apps/<cle> && cd ~/apps/<cle>
   docker exec nfc_dev_backend python manage.py ecrire_env <cle> > /tmp/env \
     && install -m 600 /tmp/env .env.dev; rm -f /tmp/env
   ./deploy.sh dev
   ```

5. **nginx** : `infrastructure/nginx.conf.example` → `~/infra/nginx/conf.d/10-<cle>.conf`,
   une adresse par client dans `server_name`, puis `nginx -t` et rechargement.

Même chose pour la production avec `_prod`, `.env.prod`, `nfc_prod_backend`
et `./deploy.sh prod`.

## Les règles à ne pas casser

Détaillées dans `nfc/docs/solution-factory/CONTRAT_SOLUTION.md`. En bref :

- Toute table métier hérite de `TenantModel`. Toute unicité métier est **par
  espace** (`UniqueConstraint(fields=["tenant", …])`), jamais `unique=True`.
- L'espace ne se lit jamais dans le corps d'une requête : il vient de l'adresse.
- Un module fermé refuse l'appel API, même à un administrateur. Cacher un
  bouton n'est pas une autorisation.
- Aucun port publié ; alias Docker en tirets ; images non-root ;
  `NEXT_PUBLIC_*` passées en argument de build.
- Le test qui compte : **deux espaces, et l'un ne voit rien de l'autre**
  (`backend/tests/test_isolation.py`, et le `tests.py` de chaque module).
