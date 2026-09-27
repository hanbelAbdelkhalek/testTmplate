from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """Ajoute un `code` stable à chaque erreur (`module_closed`, `limit_reached`…).

    Le frontend décide sur le code, jamais sur le texte : le texte est pour
    l'utilisateur et peut changer.
    """
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict) and "detail" in response.data:
        codes = exc.get_codes() if hasattr(exc, "get_codes") else None
        if isinstance(codes, str):
            response.data["code"] = codes
    return response
