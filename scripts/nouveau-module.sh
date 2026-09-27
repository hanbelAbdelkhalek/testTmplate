#!/usr/bin/env bash
# Crée un module métier dans backend/apps/<nom>, depuis backend/gabarits/module.
#
#   scripts/nouveau-module.sh ventes
#
# Le nom sert aussi de clé de module pour la plateforme (droits d'abonnement)
# et de préfixe des permissions (ventes.view, ventes.manage) : minuscules et
# chiffres seulement, sans tiret ni souligné, pour être valable partout.
set -euo pipefail

nom="${1:-}"
[[ "$nom" =~ ^[a-z][a-z0-9]{1,39}$ ]] || {
  echo "usage : $0 <nom>   (minuscules et chiffres, ex. ventes)" >&2
  exit 2
}

racine="$(cd "$(dirname "$0")/.." && pwd)"
cd "$racine/backend"
[[ -e "apps/$nom" ]] && { echo "apps/$nom existe déjà." >&2; exit 1; }

python="python"
[[ -x .venv/bin/python ]] && python=".venv/bin/python"
[[ -x .venv/Scripts/python.exe ]] && python=".venv/Scripts/python.exe"

mkdir "apps/$nom"
DEBUG=1 "$python" manage.py startapp --template=gabarits/module --name README.md "$nom" "apps/$nom"

echo
echo "Module créé : backend/apps/$nom"
echo "Reste à le brancher — voir backend/apps/$nom/README.md"
