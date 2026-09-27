# Backend Django. Construit sur le serveur (ARM64) : l'image de base publie
# les deux architectures, rien à forcer.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# curl : la sonde de santé Docker. psycopg[binary] embarque libpq, inutile
# d'installer un compilateur.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Utilisateur sans privilège, avec un répertoire personnel : gunicorn y ouvre
# son serveur de contrôle, et sans lui chaque démarrage journalise une
# erreur de permission qui masque les vraies.
RUN useradd --uid 1001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app

COPY --chown=app:app . .
RUN chmod +x entrypoint.sh

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health/ready/ || exit 1

CMD ["./entrypoint.sh"]
