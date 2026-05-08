"""Mellomvare som lagrer request i thread-local for audit-logging."""
from .utils import set_current_request, clear_current_request


class RequestAuditMiddleware:
    """
    Lagrer request-objektet i thread-local storage slik at signals
    kan hente bruker og IP uten å sende request manuelt.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_request(request)
        try:
            response = self.get_response(request)
        finally:
            clear_current_request()
        return response
