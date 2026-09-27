from django.conf import settings
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class LiveView(APIView):
    """Le processus répond. Aucune dépendance vérifiée."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class ReadyView(APIView):
    """Prêt à servir : la base répond. Sondé par Docker et par la plateforme.

    200 exactement, sans redirection, ou 503 : un déploiement n'est réussi que
    si cette route répond 200.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            return Response({"status": "unavailable", "database": "down"}, status=503)
        return Response({"status": "ok", "database": "ok"})


class VersionView(APIView):
    """Ce qui tourne. Jamais un secret."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(
            {
                "solution": settings.SOLUTION_KEY,
                "version": settings.SOLUTION_VERSION,
                "environment": settings.ENVIRONMENT,
                "release": settings.RELEASE_SHA,
            }
        )
