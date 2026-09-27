#!/usr/bin/env bash
# Crée le dépôt d'une nouvelle solution à partir de ce modèle.
#
#   scripts/nouvelle-solution.sh crm "SigmaGravity CRM"            → ../crm
#   scripts/nouvelle-solution.sh crm "SigmaGravity CRM" /chemin/crm
#
# La clé est celle du registre de la plateforme : minuscules, chiffres,
# tirets (ex. crm, pos, prise-rdv).
set -euo pipefail

cle="${1:-}"; nom="${2:-}"
[[ "$cle" =~ ^[a-z][a-z0-9-]{1,39}$ && -n "$nom" ]] || {
  echo "usage : $0 <cle> \"<Nom affiché>\" [dossier]" >&2
  exit 2
}
modele="$(cd "$(dirname "$0")/.." && pwd)"
cible="${3:-$(dirname "$modele")/$cle}"
[[ -e "$cible" ]] && { echo "$cible existe déjà." >&2; exit 1; }
base="${cle//-/_}"   # PostgreSQL : pas de tiret dans un nom de base sans guillemets

# Copie sans ce qui est local à cette machine.
mkdir -p "$cible"
tar -C "$modele" -cf - \
  --exclude=.git --exclude=backend/.venv --exclude=node_modules --exclude=.next \
  --exclude=backend/db.sqlite3 --exclude=backend/.env.local --exclude=backend/.dev-credentials \
  --exclude=__pycache__ --exclude=backend/media --exclude=backend/staticfiles --exclude=.claude \
  . | tar -C "$cible" -xf -

cd "$cible"
sed -i \
  -e "s/^  key: template$/  key: $cle/" \
  -e "s/^  displayName: SigmaGravity Template$/  displayName: $nom/" \
  -e "s/^  description: Modèle de départ des solutions SigmaGravity.$/  description: \"\"/" \
  solution.yaml
sed -i \
  -e "s/^PREFIX=template-dev$/PREFIX=$cle-dev/" \
  -e "s/^SOLUTION_KEY=template$/SOLUTION_KEY=$cle/" \
  -e "s/^APP_NAME=SigmaGravity Template$/APP_NAME=$nom/" \
  -e "s/template_dev/${base}_dev/g" \
  .env.example
sed -i -e "s/env(\"SOLUTION_KEY\", \"template\")/env(\"SOLUTION_KEY\", \"$cle\")/" backend/config/settings.py
sed -i -e "s/template-dev-frontend/$cle-dev-frontend/" infrastructure/nginx.conf.example

git init -q -b main
git add -A
git -c user.name="${GIT_AUTHOR_NAME:-$(git config user.name || echo SigmaGravity)}" \
    commit -q -m "Nouvelle solution $cle, depuis le modèle SigmaGravity"

echo "Solution « $nom » créée dans $cible"
echo "Suite : README.md, section « Brancher une nouvelle solution »."
