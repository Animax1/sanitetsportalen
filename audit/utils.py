"""Hjelpefunksjoner for revisjonslogg."""
import threading

_thread_local = threading.local()


def set_current_request(request):
    """Lagre request i thread-local storage."""
    _thread_local.request = request


def get_current_request():
    """Hent request fra thread-local storage."""
    return getattr(_thread_local, 'request', None)


def clear_current_request():
    """Fjern request fra thread-local storage."""
    _thread_local.request = None
