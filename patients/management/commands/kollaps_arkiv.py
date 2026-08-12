"""Kollaps gamle vaktarkiv til aggregert statistikk.

Etter 24 måneder slettes de arkiverte pasientradene permanent og erstattes av
den ferdig beregnede statistikken. Formålet — evaluering og planlegging av
kommende arrangementer — er da uttømt, og GDPR art. 5(1)(e) tillater ikke at
helseopplysninger på radnivå blir liggende på ubestemt tid.

Kjøres som:
  python manage.py kollaps_arkiv --dry-run     # se hva som ville skjedd
  python manage.py kollaps_arkiv               # utfør
  python manage.py kollaps_arkiv --days 900    # annen grense

**Operasjonen er irreversibel.** Etter kollaps finnes ingen opplysninger om
enkeltpasienter i arkivet. Derfor:

- Kommandoen nekter å kollapse et arkiv med mindre det finnes en
  ``arkiv``-backup tatt etter at arkivet ble opprettet. Da er slettingen
  gjenopprettbar fra backup hvis noe skulle vise seg å være galt.
- ``--dry-run`` viser nøyaktig hva som ville blitt slettet.
- Hver kollaps loggføres i AuditLog.

Settes opp som egen Railway Cron Job — bevisst ikke som del av
``purge_old_logs``, slik at en irreversibel sletting av helsedata ikke fyrer
som bieffekt av en loggopprydding. Se docs/OPPSETT_KOLLAPS_CRON.md.

Lagringstiden er begrunnet i docs/PERSONVERN_DOKUMENTASJON.md A.9.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from audit.models import AuditLog
from patients.models import ArkivertPasient, VaktArkiv
from patients.services import har_arkiv_backup_etter, kollaps_arkiv

# 24 måneder. Dekker to hele sesonger, slik at årets vakt kan sammenlignes
# med fjorårets under planleggingen før radnivået forsvinner.
DEFAULT_DAGER = 730


class Command(BaseCommand):
    help = 'Kollaps vaktarkiv eldre enn N dager til aggregert statistikk'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=DEFAULT_DAGER,
            help=f'Kollaps arkiv eldre enn N dager (standard: {DEFAULT_DAGER} = 24 mnd)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Vis hva som ville blitt kollapset, uten å slette noe',
        )
        parser.add_argument(
            '--ignorer-backup-sperre',
            action='store_true',
            default=False,
            help=(
                'Kollaps selv om det ikke finnes en arkiv-backup. '
                'Bruk kun hvis du vet hva du gjør — slettingen er irreversibel.'
            ),
        )

    def handle(self, *args, **options):
        dager = options['days']
        dry_run = options['dry_run']
        ignorer_sperre = options['ignorer_backup_sperre']

        grense = timezone.now() - timedelta(days=dager)

        kandidater = VaktArkiv.objects.filter(
            kollapset_at__isnull=True,
            importert_at__lt=grense,
        ).order_by('importert_at')

        if not kandidater.exists():
            self.stdout.write(
                f'Ingen arkiv eldre enn {dager} dager som ikke allerede er kollapset.'
            )
            return

        if dry_run:
            self.stdout.write(
                f'[Tørrkjøring] Arkiv eldre enn {dager} dager:'
            )

        kollapset = 0
        hoppet_over = 0

        for arkiv in kandidater:
            antall_rader = ArkivertPasient.objects.filter(arkiv=arkiv).count()

            if not ignorer_sperre and not har_arkiv_backup_etter(arkiv.importert_at):
                self.stdout.write(self.style.WARNING(
                    f'  HOPPET OVER «{arkiv.tittel}» ({antall_rader} pasientrader): '
                    f'ingen arkiv-backup tatt etter at arkivet ble opprettet. '
                    f'Kjør en backup av modulen «arkiv» først.'
                ))
                hoppet_over += 1
                continue

            if dry_run:
                self.stdout.write(
                    f'  Ville kollapset «{arkiv.tittel}» '
                    f'(arkivert {arkiv.importert_at:%d.%m.%Y}, '
                    f'{antall_rader} pasientrader slettes)'
                )
                kollapset += 1
                continue

            slettet = kollaps_arkiv(arkiv)

            AuditLog.objects.create(
                table_name='patients_vaktarkiv',
                record_id=arkiv.pk,
                action='UPDATE',
                field_name='kollapset_at',
                old_value='',
                new_value=(
                    f'{slettet} pasientrader slettet, erstattet av aggregat'
                ),
            )

            self.stdout.write(self.style.SUCCESS(
                f'  Kollapset «{arkiv.tittel}»: {slettet} pasientrader slettet.'
            ))
            kollapset += 1

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[Tørrkjøring fullført] {kollapset} arkiv ville blitt kollapset, '
                f'{hoppet_over} hoppet over. Ingen data ble slettet.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Ferdig: {kollapset} arkiv kollapset, {hoppet_over} hoppet over.'
            ))
