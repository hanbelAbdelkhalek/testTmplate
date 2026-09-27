"""
Crée un espace et son administrateur, sans passer par la plateforme.

Pour le développement local et les essais. En production, c'est la plateforme
qui crée les espaces (API interne signée) : elle sait qui a payé quoi.

    python manage.py creer_espace demo --host localhost --admin admin --email admin@demo.test

Le mot de passe est demandé au clavier, ou lu dans CREER_ESPACE_PASSWORD —
jamais passé en argument, où il resterait dans l'historique du terminal.
"""

import getpass
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core import solution
from apps.entitlements.services import ensure_default_modules
from apps.identity.services import AccountError, bootstrap_admin
from apps.rbac.services import ensure_default_roles
from apps.tenancy.models import Domain, Tenant


class Command(BaseCommand):
    help = "Crée un espace client et son premier administrateur (usage local)."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Nom court de l'espace (ex. demo).")
        parser.add_argument("--name", help="Nom affiché. Par défaut : le slug.")
        parser.add_argument("--host", action="append", default=[],
                            help="Nom d'hôte qui mène à l'espace. Répétable.")
        parser.add_argument("--admin", default="admin", help="Identifiant de l'administrateur.")
        parser.add_argument("--email", default="", help="E-mail de l'administrateur.")
        parser.add_argument("--demo", action="store_true", help="Espace de démonstration (données d'exemple).")

    def handle(self, *args, **opts):
        slug = opts["slug"].strip().lower()
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f"L'espace « {slug} » existe déjà.")
        hosts = opts["host"] or [f"{slug}.localhost"]
        pris = Domain.objects.filter(hostname__in=hosts).values_list("hostname", flat=True)
        if pris:
            raise CommandError(f"Hôte déjà attribué : {', '.join(pris)}")

        password = os.environ.get("CREER_ESPACE_PASSWORD") or getpass.getpass(
            f"Mot de passe de {opts['admin']} : "
        )
        with transaction.atomic():
            tenant = Tenant.objects.create(
                slug=slug, display_name=opts["name"] or slug.title(), is_demo=opts["demo"]
            )
            for i, host in enumerate(hosts):
                Domain.objects.create(tenant=tenant, hostname=host, is_primary=i == 0)
            ensure_default_roles(tenant)
            ensure_default_modules(tenant)
            try:
                bootstrap_admin(
                    tenant, name=opts["admin"].title(), username=opts["admin"],
                    email=opts["email"] or f"{opts['admin']}@{slug}.test", password=password,
                )
            except AccountError as exc:
                raise CommandError(exc.message) from exc
            if opts["demo"]:
                solution.seed_demo(tenant)

        self.stdout.write(self.style.SUCCESS(
            f"Espace « {slug} » créé — hôtes : {', '.join(hosts)} — administrateur : {opts['admin']}"
        ))
