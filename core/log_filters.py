"""Logg-filtre (F1).

`AdminEmailHandler` sender én e-post per ERROR-record. Uten demping betyr det
at en feil i en travel sti — en feilende spørring som treffes av hver request
under en vakt — kan produsere hundrevis av mailer på minutter. Da slutter man
å lese dem, og varslingen er verdiløs akkurat når den trengs.
"""
import logging
import threading
import time


class ThrottleByMessageFilter(logging.Filter):
    """Slipper gjennom maks én record per feiltype per tidsvindu.

    «Feiltype» er (logger, nivå, filnavn, linjenummer) — ikke selve teksten.
    Grunnen er at samme kodefeil ofte gir varierende meldinger (ulike
    pasient-ID-er, ulike verdier), og en tekstbasert nøkkel ville da sluppet
    gjennom hver variant som om den var ny.

    State er per prosess. Med flere Gunicorn-arbeidere kan man i verste fall få
    én mail per arbeider per vindu. Det er akseptert: alternativet er delt
    state i Redis, som gjør varslingsstien avhengig av at Redis er oppe —
    nøyaktig det man ikke vil når man varsler om at noe er galt.
    """

    def __init__(self, window_seconds=900):
        super().__init__()
        self.window_seconds = window_seconds
        self._sist_sendt = {}
        self._lock = threading.Lock()

    def _nokkel(self, record):
        return (record.name, record.levelno, record.pathname, record.lineno)

    def filter(self, record):
        nokkel = self._nokkel(record)
        na = time.monotonic()

        with self._lock:
            forrige = self._sist_sendt.get(nokkel)
            if forrige is not None and (na - forrige) < self.window_seconds:
                return False
            self._sist_sendt[nokkel] = na

            # Enkel opprydding så dicten ikke vokser ubegrenset i en
            # langtkjørende prosess.
            if len(self._sist_sendt) > 500:
                grense = na - self.window_seconds
                self._sist_sendt = {
                    k: v for k, v in self._sist_sendt.items() if v >= grense
                }

        return True
