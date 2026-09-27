#!/usr/bin/env bash
# Backend en local, SQLite, DEBUG. Prérequis : scripts/installer.sh
set -euo pipefail
cd "$(dirname "$0")/../backend"
python=".venv/bin/python"; [[ -x .venv/Scripts/python.exe ]] && python=".venv/Scripts/python.exe"
export DEBUG=1
# Variables locales facultatives (PLATFORM_SHARED_SECRET de test…). Ignoré par git.
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi
"$python" manage.py migrate --noinput
exec "$python" manage.py runserver 127.0.0.1:${BACKEND_PORT:-8000}
