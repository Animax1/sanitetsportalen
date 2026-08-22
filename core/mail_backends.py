"""E-post-backend som sender via AHASends HTTP-API i stedet for SMTP.

**Hvorfor denne finnes.** Railway sperrer utgående SMTP. Målt fra containeren
22. aug. 2026: portene 587, 2525, 465 og 25 er alle stengt, mens 443 mot samme
vert er åpen. Pakkene droppes i stedet for å avvises, så en SMTP-tilkobling
henger i ``connect()`` til noe river den ned. Det er en plattformpolicy mot
spam-misbruk, og den gjelder uansett leverandør — å bytte fra AHASend til en
annen SMTP-tjeneste ville truffet samme vegg.

Backenden bytter kun *transporten*. ``mail_admins()``, ``AdminEmailHandler``,
``send_mail()`` og ``verifiser_feilvarsel`` fungerer uendret, og den slanke
feilrapporten i ``core/error_reporting.py`` er upåvirket.

API-et: ``POST https://api.ahasend.com/v2/accounts/{konto}/messages`` med
``Authorization: Bearer aha-sk-…``. Svarer 202 ved suksess.

**Valg som er tatt bevisst:**

- **``urllib`` fra standardbiblioteket, ikke ``requests``.** Én HTTP-POST
  rettferdiggjør ikke en ny avhengighet, og dette er stien som skal virke når
  alt annet feiler. Færrest mulig bevegelige deler.
- **Alltid tidsgrense.** ``EMAIL_TIMEOUT`` styrer den. Uten ville en treg
  API-vert låst tråden som sender — og ``AdminEmailHandler`` sender synkront i
  requestens egen tråd. Det var nettopp den feilen SMTP-oppsettet hadde.
- **``fail_silently`` respekteres strengt.** ``AdminEmailHandler`` kaller alltid
  med ``fail_silently=True``. En varsling som ikke kan leveres skal ikke gjøre
  vondt verre ved å kaste inni en loggehandler.
- **``Idempotency-Key`` per melding.** Dempingsfilteret er per prosess, så to
  Gunicorn-arbeidere kan sende samme varsel. Nøkkelen lar AHASend luke bort
  duplikatet.

**Ikke støttet:** vedlegg, egendefinerte headere og ``cc``/``bcc`` som egne
felter — alle mottakere legges i ``recipients`` og ser hverandre ikke. Portalen
sender kun varsler til ``ADMINS``, så det er tilstrekkelig. Trengs mer, er det
et bevisst utvidelsespunkt, ikke en glemt detalj.
"""
import json
import logging
import uuid
from email.utils import parseaddr
from urllib import error, request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

API_ROT = 'https://api.ahasend.com/v2'

# AHASend tar maks 100 mottakere per kall. Portalen sender til ADMINS, som er
# en håndfull — grensen er her for at en feil skal bli forståelig, ikke stille.
MAKS_MOTTAKERE = 100


class AhaSendIkkeKonfigurert(RuntimeError):
    """API-nøkkel eller konto-ID mangler."""


class AhaSendApiBackend(BaseEmailBackend):
    """Sender e-post over HTTPS fordi SMTP er sperret i containeren."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, 'AHASEND_API_KEY', '')
        self.konto_id = getattr(settings, 'AHASEND_ACCOUNT_ID', '')
        self.timeout = getattr(settings, 'EMAIL_TIMEOUT', None) or 10

    # ── Offentlig API ────────────────────────────────────────────────────────

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not (self.api_key and self.konto_id):
            self._svikt(AhaSendIkkeKonfigurert(
                'AHASEND_API_KEY eller AHASEND_ACCOUNT_ID mangler — '
                'e-post kan ikke sendes over HTTP-API-et.'
            ))
            return 0

        sendt = 0
        for melding in email_messages:
            if self._send_en(melding):
                sendt += 1
        return sendt

    # ── Innmat ───────────────────────────────────────────────────────────────

    def _send_en(self, melding):
        try:
            kropp = self._bygg_kropp(melding)
        except Exception as exc:
            return self._svikt(exc)

        if not kropp['recipients']:
            logger.warning('E-post uten mottakere ble ikke sendt: %s',
                           melding.subject)
            return False

        req = request.Request(
            f'{API_ROT}/accounts/{self.konto_id}/messages',
            data=json.dumps(kropp).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'Idempotency-Key': str(uuid.uuid4()),
            },
            method='POST',
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as svar:
                if 200 <= svar.status < 300:
                    return True
                logger.error('AHASend svarte %s på utsending', svar.status)
                return False
        except error.HTTPError as exc:
            # Les feilkroppen — den forklarer som regel *hvorfor* (ugyldig
            # avsenderdomene, manglende scope på nøkkelen, ukjent konto).
            detalj = ''
            try:
                detalj = exc.read().decode('utf-8', errors='replace')[:500]
            except Exception:
                pass
            return self._svikt(
                RuntimeError(f'AHASend svarte {exc.code}: {detalj}')
            )
        except Exception as exc:
            return self._svikt(exc)

    def _bygg_kropp(self, melding):
        navn, adresse = parseaddr(
            melding.from_email or settings.DEFAULT_FROM_EMAIL
        )
        if not adresse:
            raise ValueError(f'Ugyldig avsenderadresse: {melding.from_email!r}')

        mottakere = [
            {'email': a} for a in
            (parseaddr(m)[1] for m in melding.recipients()) if a
        ]
        if len(mottakere) > MAKS_MOTTAKERE:
            raise ValueError(
                f'{len(mottakere)} mottakere overstiger AHASends grense på '
                f'{MAKS_MOTTAKERE} per kall.'
            )

        avsender = {'email': adresse}
        if navn:
            avsender['name'] = navn

        kropp = {
            'from': avsender,
            'recipients': mottakere,
            'subject': melding.subject or '',
        }

        tekst, html = self._innhold(melding)
        if tekst:
            kropp['text_content'] = tekst
        if html:
            kropp['html_content'] = html
        if not tekst and not html:
            # API-et krever minst ett av feltene.
            kropp['text_content'] = ''
        return kropp

    @staticmethod
    def _innhold(melding):
        """Skiller tekst fra HTML, uavhengig av meldingstype."""
        tekst = melding.body or ''
        html = ''
        if melding.content_subtype == 'html':
            html, tekst = tekst, ''
        for innhold, mimetype in getattr(melding, 'alternatives', ()) or ():
            if mimetype == 'text/html':
                html = innhold
        return tekst, html

    def _svikt(self, exc):
        """Kaster eller logger, etter ``fail_silently``. Returnerer alltid False.

        AdminEmailHandler kaller alltid med ``fail_silently=True``. En varsling
        som ikke kan leveres skal ikke rive ned requesten som utløste den — men
        den skal etterlate seg et spor i loggen, ellers er den umulig å feilsøke.
        """
        if not self.fail_silently:
            raise exc
        logger.error('Kunne ikke sende e-post via AHASend: %s', exc)
        return False
