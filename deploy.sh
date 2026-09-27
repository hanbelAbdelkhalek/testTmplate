#!/usr/bin/env bash
# =============================================================================
# Déploie une pile de la solution — essai ou production
# =============================================================================
#   ./deploy.sh dev     |     ./deploy.sh prod
#   ./deploy.sh dev main          ← branche imposée (celle du registre de la plateforme)
#
# Chaque pile suit sa branche. Passer de l'essai à la production est une
# fusion faite à la main quand le travail est prêt — jamais l'effet de bord
# d'un push.
set -euo pipefail

# --- Branches par défaut, quand aucune n'est passée en argument ---------------
BRANCHE_dev="dev"
BRANCHE_prod="main"
# -----------------------------------------------------------------------------

PILE="${1:-}"
case "$PILE" in
  dev|prod) ;;
  *) echo "usage : $0 dev|prod [branche]" >&2; exit 2 ;;
esac
BRANCHE_VAR="BRANCHE_$PILE"
BRANCHE="${2:-${!BRANCHE_VAR}}"
[[ "$BRANCHE" =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "Branche invalide : $BRANCHE" >&2; exit 2; }

RACINE="$(cd "$(dirname "$0")" && pwd)"
cd "$RACINE"
export ENV_FILE="$RACINE/.env.$PILE"

echo "=== 1. Code (branche $BRANCHE) ==="
git fetch --quiet origin "$BRANCHE"
git reset --quiet --hard "origin/$BRANCHE"
export RELEASE_SHA="$(git rev-parse --short HEAD)"
echo "    $(git log --oneline -1)"

echo "=== 2. Réglages ==="
[[ -f "$ENV_FILE" ]] || { echo "    ERREUR : $ENV_FILE absent. Ce script n'invente pas les secrets."; exit 1; }
lire() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | sed -e "s/^'//" -e "s/'$//"; }
for cle in PREFIX ENVIRONMENT SOLUTION_KEY SECRET_KEY DATABASE_URL PLATFORM_SHARED_SECRET; do
  [[ -n "$(lire "$cle")" ]] || { echo "    ERREUR : $cle absente ou vide dans $ENV_FILE"; exit 1; }
done
PREFIX="$(lire PREFIX)"; export PREFIX
export APP_NAME="$(lire APP_NAME)"
BASE="$(lire DATABASE_URL | sed -E 's|.*/([^/?]+)(\?.*)?$|\1|')"
# Une inversion ici enverrait les migrations de l'essai sur la base des vrais
# clients : mieux vaut refuser de démarrer que de s'en apercevoir après.
[[ "$(lire ENVIRONMENT)" == "$PILE" ]] || { echo "    ERREUR : ENVIRONMENT ≠ $PILE dans $ENV_FILE"; exit 1; }
[[ "$PREFIX" == *"$PILE"* ]]           || { echo "    ERREUR : PREFIX ($PREFIX) ne désigne pas la pile $PILE"; exit 1; }
[[ "$BASE" == *"_$PILE" ]]             || { echo "    ERREUR : la base $BASE ne se termine pas par _$PILE"; exit 1; }
[[ "$PREFIX" =~ ^[a-z0-9-]+$ ]]        || { echo "    ERREUR : PREFIX en minuscules, chiffres et tirets"; exit 1; }
echo "    pile $PREFIX, base $BASE"

echo "=== 3. Base de données ==="
# Créée si absente, jamais recréée. Le rôle et son mot de passe sont posés
# une fois à la main (voir README, « Première mise en service »).
docker exec global_postgres psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$BASE'" | grep -q 1 \
  || { echo "    ERREUR : la base $BASE n'existe pas. Voir README, « Première mise en service »."; exit 1; }
echo "    base $BASE présente"

echo "=== 4. Volume ==="
# Django tourne en uid 1001. Docker ne recopie les droits de l'image que dans
# un volume vide.
docker volume create "${PREFIX}_media" >/dev/null
docker run --rm -v "${PREFIX}_media":/m alpine chown -R 1001:1001 /m
echo "    ${PREFIX}_media à l'uid 1001"

echo "=== 5. Construction ==="
docker compose -p "$PREFIX" build --quiet backend frontend

echo "=== 6. Migrations ==="
# Une seule fois, avant de remplacer les conteneurs, sous verrou : deux
# déploiements simultanés n'appliquent pas le même schéma en même temps.
flock "/tmp/deploy-${PREFIX}.lock" \
  docker compose -p "$PREFIX" run --rm --no-deps backend python manage.py migrate --noinput

echo "=== 7. Démarrage ==="
docker compose -p "$PREFIX" up -d --remove-orphans

echo "=== 8. Vérification ==="
# Réussi seulement quand les deux sondes de santé répondent.
for c in "${PREFIX}_backend" "${PREFIX}_frontend"; do
  for _ in $(seq 1 45); do
    etat="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$c" 2>/dev/null || echo absent)"
    [[ "$etat" == "healthy" ]] && break
    [[ "$etat" == "unhealthy" || "$etat" == "exited" || "$etat" == "absent" ]] && break
    sleep 2
  done
  printf "    %-30s %s\n" "$c" "$etat"
  [[ "$etat" == "healthy" ]] || { echo "    ÉCHEC — journal :"; docker logs --tail 40 "$c"; exit 1; }
done
docker exec "${PREFIX}_backend" curl -fsS http://127.0.0.1:8000/api/version/ && echo
echo "    pile $PREFIX en service ($RELEASE_SHA)"
