#!/usr/bin/env bash
# Frontend en local, relié au backend local.
set -euo pipefail
cd "$(dirname "$0")/../frontend"
export DJANGO_API_URL="http://127.0.0.1:${BACKEND_PORT:-8000}/api"
exec npx next dev -p "${PORT:-3100}"
