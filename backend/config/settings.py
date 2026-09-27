"""
Réglages de la solution. Tout vient de l'environnement : le même code tourne
en local, sur la pile d'essai et en production, seules les variables changent.

Les variables se saisissent dans l'écran « Gestion des solutions » de la
plateforme, qui rend le fichier .env de chaque pile (`manage.py ecrire_env`).
La liste complète est dans `.env.example` à la racine du dépôt.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)
TESTING = "test" in sys.argv[1:2]

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if not (DEBUG or TESTING):
        # Une clé par défaut en production signerait les sessions avec une
        # valeur publique : mieux vaut refuser de démarrer.
        raise ImproperlyConfigured("SECRET_KEY est obligatoire hors DEBUG.")
    SECRET_KEY = "dev-only-insecure-key-change-me-0123456789"

# --- La solution --------------------------------------------------------------
SOLUTION_KEY = env("SOLUTION_KEY", "template")
SOLUTION_VERSION = env("SOLUTION_VERSION", "0.1.0")
# `dev` ou `prod`. Affiché par /api/version/, jamais utilisé pour décider d'une
# autorisation.
ENVIRONMENT = env("ENVIRONMENT", "dev")
RELEASE_SHA = env("RELEASE_SHA", "local")

# --- Accès -------------------------------------------------------------------
# Django n'est joint que par le frontend, sur le réseau Docker, par son alias.
# Les noms publics des clients n'arrivent jamais dans l'en-tête Host : ils sont
# dans X-Forwarded-Host, posé par le frontend et lu par le middleware des
# espaces.
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

# Pas de redirection HTTPS ici : le TLS est terminé par Cloudflare, et Django
# est appelé en HTTP clair sur le réseau interne. Une redirection renverrait
# chaque appel du frontend vers une adresse qui ne parle pas TLS — et le
# frontend servirait en silence des pages vides.
SECURE_SSL_REDIRECT = False
SECURE_CONTENT_TYPE_NOSNIFF = True

# --- Plateforme SigmaGravity --------------------------------------------------
# Secret partagé avec la plateforme, qui signe ses appels internes (HMAC).
# Absent : les routes /api/internal/ répondent 503 plutôt que d'être ouvertes.
PLATFORM_SHARED_SECRET = env("PLATFORM_SHARED_SECRET")
PLATFORM_KEY_ID = env("PLATFORM_KEY_ID", "platform-v1")
PLATFORM_SIGNATURE_TOLERANCE_SECONDS = 300
# Domaine des adresses clients : un espace créé par la plateforme reçoit
# l'adresse <nom>.<ROOT_DOMAIN>.
ROOT_DOMAIN = env("ROOT_DOMAIN", "sigmagravity.com")

# En local uniquement : l'espace servi quand la requête ne porte aucun hôte
# connu (localhost). Ignoré hors DEBUG.
DEFAULT_TENANT_SLUG = env("DEFAULT_TENANT_SLUG") if DEBUG else ""

# --- Applications -------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    # Socle commun à toutes les solutions. Ne pas le modifier par solution :
    # c'est ce qui permet à la plateforme de les piloter toutes de la même
    # façon.
    "apps.core",
    "apps.tenancy",
    "apps.rbac",
    "apps.identity",
    "apps.entitlements",
    "apps.audit",
    "apps.provisioning",
    # Le métier de la solution. `catalog` est un exemple complet : le garder
    # comme modèle, puis le remplacer.
    "apps.catalog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Avant toute vue : une requête sans espace connu n'atteint aucun code
    # métier.
    "apps.tenancy.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

# --- Base de données ----------------------------------------------------------
# PostgreSQL partagé du serveur (`global_postgres`), une base par pile :
# <solution>_dev et <solution>_prod. SQLite en local si DATABASE_URL est vide.
def _database_url() -> str:
    # DATABASE_URL d'abord ; sinon les variables séparées (DB_HOST, DB_NAME…),
    # que la plateforme génère aussi, avec le même mot de passe.
    if env("DATABASE_URL"):
        return env("DATABASE_URL")
    if env("DB_NAME"):
        from urllib.parse import quote

        return (
            f"postgres://{quote(env('DB_USER'), safe='')}:{quote(env('DB_PASSWORD'), safe='')}"
            f"@{env('DB_HOST', 'global_postgres')}:{env('DB_PORT', '5432')}/{env('DB_NAME')}"
        )
    return f"sqlite:///{BASE_DIR / 'db.sqlite3'}"


DATABASES = {
    "default": dj_database_url.parse(
        _database_url(),
        conn_max_age=60,
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Mots de passe -----------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- API ---------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.identity.authentication.TenantJWTAuthentication",
    ],
    # Toute vue exige un compte de l'espace, plus ce qu'elle déclare
    # (`module`, `permissions`). Une vue publique doit le dire explicitement.
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.rbac.permissions.SolutionPermission",
    ],
    # JSON seulement : l'API navigable afficherait des formulaires à qui ouvre
    # une route dans un navigateur.
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
    "DEFAULT_THROTTLE_RATES": {"login": env("LOGIN_RATE", "20/hour")},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "UPDATE_LAST_LOGIN": True,
}

# --- Divers ------------------------------------------------------------------
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Casablanca"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
