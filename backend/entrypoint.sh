#!/bin/sh
# Démarrage du backend. Les migrations ne se lancent PAS ici : le script de
# déploiement les passe une seule fois, avant de remplacer les conteneurs.
# Les lancer à chaque démarrage ferait migrer deux workers en même temps.
set -e

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  --access-logfile - \
  --error-logfile -
