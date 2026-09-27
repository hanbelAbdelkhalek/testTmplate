#!/usr/bin/env bash
# Installe les dépendances pour travailler en local.
set -euo pipefail
racine="$(cd "$(dirname "$0")/.." && pwd)"

cd "$racine/backend"
[[ -d .venv ]] || python -m venv .venv
pip=".venv/bin/pip"; [[ -x .venv/Scripts/pip.exe ]] && pip=".venv/Scripts/pip.exe"
"$pip" install -q -r requirements.txt
echo "backend : dépendances installées"

cd "$racine/frontend"
npm ci --silent
echo "frontend : dépendances installées"
