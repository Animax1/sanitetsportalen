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


def ikke_under_loaddata(fn):
    """Hopp over signalet når raden kommer fra en fixture (`loaddata`).

    Django sender ``raw=True`` på `pre_save`/`post_save` når `loaddata` skriver
    en rad. Det betyr: **denne raden kommer fra en fil, ikke fra noen som
    gjorde noe.** Applikasjonslogikk skal ikke kjøre da, og det er ikke et
    finpuss — det er to reelle problemer:

    1. **Gjenoppretting feiler.** Handlerne leser relaterte objekter for å
       skrive hva som ble endret. `loaddata` laster radene i filas rekkefølge,
       så et `Vaktpost` kan komme før sitt `Mannskap` — og da slår oppslaget
       feil med `Mannskap matching query does not exist`, midt i en
       gjenoppretting. Det var nettopp dette som stoppet den første hele
       databasebackupen 13. sep. 2026.
    2. **Auditsporet blir støy.** Uten vakten skriver en gjenoppretting av
       tusen pasienter tusen «endret»-rader, uten en bruker som endret noe.
       Sporet skal si hva folk har gjort, ikke hva en fil inneholdt.

    Selve gjenopprettingen logges av `backup_admin_restore_view` — én rad som
    sier hvem som gjenopprettet hva. Det er den riktige oppføringen.

    Virker på begge formene: Django sender alle signalargumenter som
    nøkkelord, så `created` følger med i ``kwargs`` for `post_save`.
    """
    import functools

    @functools.wraps(fn)
    def _vakt(sender, instance=None, **kwargs):
        if kwargs.get('raw'):
            return None
        return fn(sender, instance=instance, **kwargs)

    return _vakt
