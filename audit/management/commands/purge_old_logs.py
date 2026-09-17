"""Management-kommando for å håndheve lagringstidene i personvernprotokollen.

Rydder:
  - ``AuditLog`` og ``LoginEvent``  – standard 730 dager (2 år)
  - ``core.Notification``           – standard 30 dager
  - **modulenes egne fristdata** via ``core.opprydding``-registeret
    (KO-loggen, 730 dager — se ``ko/opprydding.py``)

Kjøres som:
  python manage.py purge_old_logs                      # bruk standardgrensene
  python manage.py purge_old_logs --days 365           # annen grense for logger
  python manage.py purge_old_logs --notification-days 7
  python manage.py purge_old_logs --dry-run            # rapporter uten å slette

Kjøres av Railway Cron. Grensene ligger som defaults her, ikke som flagg i
cron-jobben, slik at det finnes én sannhet — og slik at en endring av
lagringstid skjer i kode som kan revideres, ikke i en skjult jobbkonfigurasjon.

**`--days` gjelder rammeverkets tabeller og rører ikke handlerne.** Modulenes
frister eies av modulene, fordi det er modulen som vet hva dataene er — ett
flagg som stilte på to helt ulike lagringstider samtidig ville vært en felle
den dagen noen brukte det. Se `core/opprydding.py`.

**Jobben kan ikke importere `ko` direkte.** `audit/` er rammeverk og måles av
`core/tests_avhengighetsretning.py`; en cron-jobb er ingen unntaksgrunn.
Registeret er den samme mekanismen som driftsdashbordet og
portalinnstillingene bruker.

Lagringstidene er begrunnet i docs/PERSONVERN_DOKUMENTASJON.md A.9.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from django.core.management.base import CommandError

from accounts.models import LoginEvent
from audit.models import AuditLog
from core.kommando import lesbar_dbfeil
from core.models import Notification
from core.opprydding import all_handlers

# Audit- og innloggingslogg: 2 år. Systemet er ikke et journalsystem (se A.4),
# så det foreligger ingen journalrettslig plikt som forlenger fristen. Perioden
# er satt ut fra behovet for å kunne oppklare sikkerhetshendelser i ettertid.
DEFAULT_LOG_DAYS = 730

# Varsler er rene driftsmeldinger ("du er satt på pasient #42") uten
# dokumentasjonsverdi etter vakten.
DEFAULT_NOTIFICATION_DAYS = 30


class Command(BaseCommand):
    help = 'Slett gamle revisjonslogger, innloggingshendelser og varsler'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=DEFAULT_LOG_DAYS,
            help=(
                f'Slett audit-logger og innloggingshendelser eldre enn N dager '
                f'(standard: {DEFAULT_LOG_DAYS} = 2 år)'
            ),
        )
        parser.add_argument(
            '--notification-days',
            type=int,
            default=DEFAULT_NOTIFICATION_DAYS,
            help=(
                f'Slett varsler eldre enn N dager '
                f'(standard: {DEFAULT_NOTIFICATION_DAYS})'
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Rapporter antall som ville bli slettet uten å faktisk slette',
        )

    def handle(self, *args, **options):
        # Én lesbar linje i cron-loggen framfor fire stablede tracebacks —
        # se core/kommando.py. Jobben er fortsatt rød og avslutter med kode 1.
        with lesbar_dbfeil('ingenting ble slettet', navn='purge_old_logs'):
            self._rydd(options)

    def _rydd(self, options):
        days = options['days']
        notification_days = options['notification_days']
        dry_run = options['dry_run']

        now = timezone.now()
        log_cutoff = now - timedelta(days=days)
        notification_cutoff = now - timedelta(days=notification_days)

        if dry_run:
            self.stdout.write('[Tørrkjøring] Viser hva som ville blitt slettet:')

        self._purge(
            LoginEvent.objects.filter(created_at__lt=log_cutoff),
            label='login-events', days=days, dry_run=dry_run,
        )
        self._purge(
            AuditLog.objects.filter(created_at__lt=log_cutoff),
            label='audit-logger', days=days, dry_run=dry_run,
        )
        self._purge(
            Notification.objects.filter(created_at__lt=notification_cutoff),
            label='varsler', days=notification_days, dry_run=dry_run,
        )

        self._moduler(now, dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '[Tørrkjøring fullført] Ingen data ble slettet. '
                'Kjør uten --dry-run for å slette.'
            ))

    def _moduler(self, now, dry_run):
        """Kjør modulenes egne oppryddinger.

        **Én feilende handler stopper ikke de andre, men jobben blir rød.**
        Begge halvdelene er valg. Å avbryte på den første ville latt en modul
        med en ødelagt spørring holde alle de andre lagringstidene
        uhåndhevet — stille, for ingen ser på mens jobben kjører. Og å svelge
        feilen ville gitt en grønn jobb som ikke gjorde det den sier, som er
        nøyaktig fella `DATABASE_URL`-sjekken i `settings.py` finnes for.
        """
        feilet = []
        for handler in all_handlers():
            dager = handler.frist_dager()
            try:
                if dry_run:
                    antall = handler.antall_utlopte(now)
                    self.stdout.write(
                        f'  Ville slettet {antall} {handler.etikett} eldre enn '
                        f'{dager} dager.')
                else:
                    antall = handler.rydd(now)
                    self.stdout.write(self.style.SUCCESS(
                        f'Slettet {antall} {handler.etikett} eldre enn '
                        f'{dager} dager.'))
            except Exception as feil:   # noqa: BLE001 — se docstringen
                feilet.append(f'{handler.slug}: {feil}')
                self.stderr.write(self.style.ERROR(
                    f'Opprydding feilet for «{handler.slug}»: {feil}'))
        if feilet:
            raise CommandError(
                'Én eller flere modulers opprydding feilet, og lagringstiden '
                'er ikke håndhevet for dem: ' + '; '.join(feilet))

    def _purge(self, queryset, *, label, days, dry_run):
        """Slett (eller rapporter) én kategori. Returnerer antall."""
        count = queryset.count()

        if dry_run:
            self.stdout.write(
                f'  Ville slettet {count} {label} eldre enn {days} dager.'
            )
            return count

        queryset.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Slettet {count} {label} eldre enn {days} dager.'
        ))
        return count
