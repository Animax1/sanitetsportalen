"""Kollaps gamle vaktarkiv til aggregert statistikk.

Etter 24 måneder slettes de arkiverte radene permanent og erstattes av den
ferdig beregnede statistikken. Formålet — evaluering og planlegging av
kommende arrangementer — er da uttømt, og GDPR art. 5(1)(e) tillater ikke at
helseopplysninger på radnivå blir liggende på ubestemt tid.

Kjøres som:
  python manage.py kollaps_arkiv --dry-run           # se hva som ville skjedd
  python manage.py kollaps_arkiv                     # utfør, alle moduler
  python manage.py kollaps_arkiv --modul oppdrag     # kun én modul
  python manage.py kollaps_arkiv --days 900          # annen grense

**Kommandoen går gjennom `core.arkiv`-registeret**, ikke gjennom
pasientmodulen. Den ble skrevet for `VaktArkiv` alene; fra fase 7 av
oppdragsmodulen finnes to arkiver, og en kommando som bare kjente det ene
ville latt oppdragsarkivet ligge til noen oppdaget det. Grensen kan settes per
modul via `BaseArkivHandler.retention_dager` — `--days` overstyrer alle.

Fila ligger fortsatt i pasientmodulen fordi cron-jobben peker hit
(`docs/OPPSETT_KOLLAPS_CRON.md`); å bytte kommandonavn ville stoppet en
planlagt sletting uten at noen fikk beskjed.

**Operasjonen er irreversibel.** Etter kollaps finnes ingen opplysninger om
enkeltpersoner i arkivet. Derfor:

- Kommandoen nekter å kollapse et arkiv med mindre det finnes en backup av
  modulens arkiv tatt etter at arkivet ble opprettet. Da er slettingen
  gjenopprettbar hvis noe skulle vise seg å være galt.
- ``--dry-run`` viser nøyaktig hva som ville blitt slettet.
- Hver kollaps loggføres i AuditLog.

Settes opp som egen Railway Cron Job — bevisst ikke som del av
``purge_old_logs``, slik at en irreversibel sletting av helsedata ikke fyrer
som bieffekt av en loggopprydding. Se docs/OPPSETT_KOLLAPS_CRON.md.

Lagringstiden er begrunnet i docs/PERSONVERN_DOKUMENTASJON.md A.9.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from core.kommando import lesbar_dbfeil
from django.utils import timezone

from audit.models import AuditLog
from core.arkiv import all_handlers, get_handler, har_backup_etter, kollaps


class Command(BaseCommand):
    help = 'Kollaps vaktarkiv eldre enn N dager til aggregert statistikk'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help=(
                'Kollaps arkiv eldre enn N dager. Uten flagget bruker hver '
                'modul sin egen `retention_dager` (standard 730 = 24 mnd).'
            ),
        )
        parser.add_argument(
            '--modul',
            default=None,
            help='Kjør kun for én modul (arkiv-handlerens slug).',
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
                'Kollaps selv om det ikke finnes en backup. Bruk kun hvis du '
                'vet hva du gjør — slettingen er irreversibel.'
            ),
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        ignorer_sperre = options['ignorer_backup_sperre']

        if options['modul']:
            handler = get_handler(options['modul'])
            if handler is None:
                kjente = ', '.join(sorted(h.slug for h in all_handlers())) or 'ingen'
                raise CommandError(
                    f'Ukjent modul «{options["modul"]}». Registrerte: {kjente}.')
            handlere = [handler]
        else:
            handlere = sorted(all_handlers(), key=lambda h: h.slug)

        if not handlere:
            self.stdout.write('Ingen arkiv-handlere er registrert.')
            return

        totalt_kollapset = 0
        totalt_hoppet = 0
        # Kollapsen er irreversibel, så en halvveis kjøring er verdt å si
        # tydelig fra om: meldingen navngir hva som *ikke* ble gjort.
        # Se core/kommando.py.
        with lesbar_dbfeil('ingen arkiv ble kollapset'):
            for handler in handlere:
                kollapset, hoppet = self._kjor_modul(
                    handler, options['days'], dry_run, ignorer_sperre)
                totalt_kollapset += kollapset
                totalt_hoppet += hoppet

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[Tørrkjøring fullført] {totalt_kollapset} arkiv ville blitt '
                f'kollapset, {totalt_hoppet} hoppet over. Ingen data ble slettet.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Ferdig: {totalt_kollapset} arkiv kollapset, '
                f'{totalt_hoppet} hoppet over.'
            ))

    def _kjor_modul(self, handler, days, dry_run, ignorer_sperre):
        dager = days if days is not None else handler.retention_dager
        grense = timezone.now() - timedelta(days=dager)
        navn = handler.display_name or handler.slug

        kandidater = list(handler.kandidater(grense))
        if not kandidater:
            self.stdout.write(
                f'{navn}: ingen arkiv eldre enn {dager} dager som ikke '
                f'allerede er kollapset.'
            )
            return 0, 0

        if dry_run:
            self.stdout.write(f'[Tørrkjøring] {navn} — eldre enn {dager} dager:')
        else:
            self.stdout.write(f'{navn} — eldre enn {dager} dager:')

        kollapset = 0
        hoppet_over = 0

        for arkiv in kandidater:
            antall_rader = handler.antall_rader(arkiv)

            if not ignorer_sperre and not har_backup_etter(
                    handler, arkiv.importert_at):
                self.stdout.write(self.style.WARNING(
                    f'  HOPPET OVER «{arkiv.tittel}» ({antall_rader} rader): '
                    f'ingen backup av modulen «{handler.backup_slug}» tatt '
                    f'etter at arkivet ble opprettet. Kjør en backup først.'
                ))
                hoppet_over += 1
                continue

            if dry_run:
                self.stdout.write(
                    f'  Ville kollapset «{arkiv.tittel}» '
                    f'(arkivert {arkiv.importert_at:%d.%m.%Y}, '
                    f'{antall_rader} rader slettes)'
                )
                kollapset += 1
                continue

            slettet = kollaps(handler, arkiv)

            AuditLog.objects.create(
                table_name=arkiv._meta.db_table,
                record_id=arkiv.pk,
                action='UPDATE',
                field_name='kollapset_at',
                old_value='',
                new_value=f'{slettet} rader slettet, erstattet av aggregat',
            )

            self.stdout.write(self.style.SUCCESS(
                f'  Kollapset «{arkiv.tittel}»: {slettet} rader slettet.'
            ))
            kollapset += 1

        return kollapset, hoppet_over
