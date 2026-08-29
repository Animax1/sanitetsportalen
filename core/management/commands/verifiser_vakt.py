"""Kontroller vakt-koblingen — kjøres mot prod mellom deploy 1 og 2.

Samme rolle som `verifiser_modultilgang` hadde i rollemodellen: deploy 2 gjør
`Vakt` til eneste fasit, og DENNE kommandoen er beviset på at fasiten stemmer
med `year` mens begge finnes. Etter deploy 2 kan sammenligningen ikke tas om
igjen — da er `year` borte fra radene.

Les-only. Endrer ingenting.

Modellene slås opp via `apps.get_model`, ikke importert: en driftskommando i
`core` som importerte `patients` og `oppdrag` ville snudd avhengighets-
retningen for hele appen for én inspeksjonsjobb. Oppslaget skjer i `handle()`,
ved kjøring, og binder ingenting ved oppstart.
"""
from django.apps import apps
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Kontroller at vakt-FK-ene stemmer med year, før deploy 2'

    def _feil(self, melding):
        self.funn += 1
        self.stdout.write(self.style.ERROR(f'  FEIL: {melding}'))

    def handle(self, *args, **options):
        Vakt = apps.get_model('core', 'Vakt')
        Patient = apps.get_model('patients', 'Patient')
        VaktArkiv = apps.get_model('patients', 'VaktArkiv')
        AppSetting = apps.get_model('patients', 'AppSetting')
        Oppdrag = apps.get_model('oppdrag', 'Oppdrag')

        self.funn = 0

        # ── Rader uten vakt ──────────────────────────────────────────────
        # Arkiver telles ikke som feil: NULL der betyr «fra før grupperingen».
        for navn, qs in (
            ('pasienter', Patient.objects.filter(vakt__isnull=True)),
            ('oppdrag', Oppdrag.objects.filter(vakt__isnull=True)),
        ):
            antall = qs.count()
            if antall:
                self._feil(f'{antall} {navn} uten vakt. Deploy 2 setter '
                           f'NOT NULL og vil feile på disse.')
        arkiv_uten = VaktArkiv.objects.filter(vakt__isnull=True).count()
        if arkiv_uten:
            self.stdout.write(
                f'  Info: {arkiv_uten} arkiv uten vakt (fra før grupperingen '
                f'— i orden).')

        # ── year må stemme med vakta ─────────────────────────────────────
        # Selve kontrakten i deploy 1: FK-en skrives, `year` leses, og de to
        # skal aldri være uenige. Er de det, har en skrivesti glemt vakta.
        from django.db.models import F
        for navn, Modell, aarfelt in (
            ('pasienter', Patient, 'year'),
            ('oppdrag', Oppdrag, 'year'),
            ('arkiv', VaktArkiv, 'year_snapshot'),
        ):
            avvik = (Modell.objects.filter(vakt__isnull=False)
                     .exclude(**{aarfelt: F('vakt__year')})
                     .count())
            if avvik:
                self._feil(f'{avvik} {navn} der {aarfelt} ikke stemmer med '
                           f'vaktas år.')

        # ── Pekeren ──────────────────────────────────────────────────────
        raa = AppSetting.objects.filter(key='aktiv_vakt_id').first()
        if raa is None:
            self.stdout.write(
                '  Info: aktiv_vakt_id er ikke satt. Settes ved første '
                'registrering (lat opprettelse) — bare et funn hvis '
                'registrering er i gang.')
        else:
            try:
                vakt = Vakt.objects.get(pk=int(raa.value))
                if not vakt.er_aktiv:
                    self._feil(f'aktiv_vakt_id peker på «{vakt.navn}», som '
                               f'ikke er aktiv.')
                else:
                    self.stdout.write(f'  Aktiv vakt: «{vakt.navn}» '
                                      f'(year={vakt.year}).')
            except (Vakt.DoesNotExist, TypeError, ValueError):
                self._feil(f'aktiv_vakt_id={raa.value!r} peker på en vakt '
                           f'som ikke finnes.')

        # ── Forhåndssjekk for deploy 2-sperrene ──────────────────────────
        # (vakt, pasientnummer) og (vakt, oppdragsnummer) blir unike. Finnes
        # kollisjoner nå, feiler den migrasjonen — bedre å vite det her.
        from django.db.models import Count
        for navn, Modell, felt in (
            ('pasientnummer', Patient, 'pasientnummer'),
            ('oppdragsnummer', Oppdrag, 'oppdragsnummer'),
        ):
            dubletter = (Modell.objects.filter(vakt__isnull=False)
                         .values('vakt', felt)
                         .annotate(n=Count('id')).filter(n__gt=1).count())
            if dubletter:
                self._feil(f'{dubletter} {navn}-kollisjoner innenfor samme '
                           f'vakt. Deploy 2-sperren vil feile.')

        # ── Oppsummering ─────────────────────────────────────────────────
        self.stdout.write(f'\n  Vakter i basen: {Vakt.objects.count()}')
        for vakt in Vakt.objects.order_by('year'):
            pas = Patient.objects.filter(vakt=vakt).count()
            opp = Oppdrag.objects.filter(vakt=vakt).count()
            ark = VaktArkiv.objects.filter(vakt=vakt).count()
            self.stdout.write(
                f'    «{vakt.navn}» (year={vakt.year}, '
                f'{"aktiv" if vakt.er_aktiv else "avsluttet"}): '
                f'{pas} pasienter, {opp} oppdrag, {ark} arkiv')

        if self.funn:
            self.stdout.write(self.style.ERROR(
                f'\n{self.funn} funn. Deploy 2 skal IKKE kjøres før disse '
                f'er rettet.'))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS('\nIngen funn. Klart for deploy 2.'))
