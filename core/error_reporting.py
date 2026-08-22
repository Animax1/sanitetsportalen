"""Slank feilrapport for e-postvarselet ved uhåndterte feil.

Django gjenbruker feilsidens mal (``technical_500.txt``) til varslings-e-posten.
Den malen er skrevet for en utvikler som sitter med DEBUG på og trenger å se alt
— den dumper hele ``Settings:``-tabellen og hele ``META:``-tabellen. I en
e-post er det rundt 13 av 14 KB støy, og det er et ganske detaljert bilde av
systemet som forlater serveren hver gang noe kræsjer.

Denne rapportøren tar med det som faktisk trengs for å forstå en feil: hva som
skjedde, hvor, hvem det traff, og når. Ikke konfigurasjonen.

**Hva som bevisst er utelatt, og hvorfor:**

- ``Settings:`` — hemmelighetene var maskert, men resten er en konfigurasjons-
  oversikt varselet ikke trenger. Den som feilsøker har `settings.py` foran seg.
- ``META:`` — hele WSGI-miljøet. Vi plukker ut de tre feltene som forklarer noe
  (IP, nettleser, referer) og lar resten ligge.
- ``GET``/``POST``/``COOKIES`` — **dette er det viktigste fravalget.** En POST
  mot pasient-API-et har kliniske opplysninger i kroppen. De skal ikke sendes
  ut av systemet i en e-post, uansett hvor nyttige de er å feilsøke med.
- Lokale variabler — ``technical_500.txt`` har dem ikke, og vi legger dem ikke
  til. Samme begrunnelse: en stackramme i en pasientvisning har pasientdata i
  minnet. Det er også derfor ``include_html=False`` står i LOGGING — HTML-malen
  *har* lokale variabler.

Brukernavnet tas med. Det er personopplysning, men mottakeren er allerede
behandlingsansvarlig, og «hvem opplevde feilen» er ofte det som skiller en
reell feil fra en tilfeldighet.

Rapportøren faller tilbake til Djangos egen ved enhver feil i seg selv. En
loggehandler som kaster, tar med seg varslingen den skulle levere.
"""
from django.views.debug import ExceptionReporter


class SlankExceptionReporter(ExceptionReporter):
    """Traceback og forespørselskontekst. Ingen settings, ingen skjemadata."""

    # Feltene fra META som forklarer noe om hendelsen.
    META_FELTER = (
        ('REMOTE_ADDR', 'Klient-IP'),
        ('HTTP_USER_AGENT', 'Nettleser'),
        ('HTTP_REFERER', 'Kom fra'),
    )

    def get_traceback_text(self):
        try:
            return self._slank_rapport()
        except Exception:
            # Heller Djangos fyldige rapport enn ingen rapport.
            return super().get_traceback_text()

    def _slank_rapport(self):
        from django.utils import timezone

        linjer = []
        exc_type = getattr(self.exc_type, '__name__', str(self.exc_type))
        linjer.append(f'{exc_type}: {self.exc_value}')
        linjer.append('')
        linjer.append(f'{"Tidspunkt":<11}: {timezone.localtime():%Y-%m-%d %H:%M:%S %Z}')

        if self.request is not None:
            linjer.append(
                f'{"Forespørsel":<11}: {self.request.method} '
                f'{self.request.get_full_path()}'
            )
            linjer.append(f'{"Bruker":<11}: {self._bruker()}')
            for nokkel, etikett in self.META_FELTER:
                verdi = self.request.META.get(nokkel)
                if verdi:
                    linjer.append(f'{etikett:<11}: {verdi}')
        else:
            linjer.append(
                f'{"Forespørsel":<11}: (ingen — feilen oppsto utenfor en request)'
            )

        linjer.append('')
        linjer.append('Traceback:')
        linjer.append(self._traceback_tekst())
        linjer.append('')
        linjer.append(
            'Konfigurasjon og skjemadata er bevisst utelatt fra dette varselet. '
            'Se core/error_reporting.py.'
        )
        return '\n'.join(linjer)

    def _bruker(self):
        """Brukernavn og rolle, uten å kunne velte rapporten."""
        try:
            bruker = getattr(self.request, 'user', None)
            if bruker is None:
                return '(ukjent — auth-middleware kjørte ikke)'
            if not bruker.is_authenticated:
                return '(ikke innlogget)'
            rolle = getattr(bruker, 'role', None)
            return f'{bruker.get_username()}' + (f' (rolle: {rolle})' if rolle else '')
        except Exception:
            return '(kunne ikke avgjøres)'

    def _traceback_tekst(self):
        """Selve stacktracen, uten lokale variabler."""
        import traceback
        if self.exc_type is None:
            return '(ingen exception)'
        return ''.join(
            traceback.format_exception(self.exc_type, self.exc_value, self.tb)
        ).rstrip()
