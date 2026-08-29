"""Kontroller vakt-koblingen.

Skrevet for vinduet mellom deploy 1 og 2, der den sammenlignet `year` på
radene mot vaktas år. Den kontrollen er **fjernet, ikke gjemt**: `year` finnes
ikke på radene etter deploy 2, og en sammenligning som alltid svarer grønt er
verre enn ingen kontroll — samme grep som §10.1-tellingen i rollemodellen.

Det som står igjen er det kommandoen fortsatt kan svare på: pekeren, arkivets
frosne år mot vaktas, og oversikten per vakt.

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

        # Skjemaet garanterer NOT NULL på Patient/Oppdrag siden deploy 2.
        # Arkivets FK er nullbar for godt: NULL betyr «fra før grupperingen».
        arkiv_uten = VaktArkiv.objects.filter(vakt__isnull=True).count()
        if arkiv_uten:
            self.stdout.write(
                f'  Info: {arkiv_uten} arkiv uten vakt (fra før grupperingen '
                f'— i orden).')

        # Arkivets frosne år mot vaktas — eneste year-sammenligning som
        # fortsatt har to kilder å sammenligne.
        from django.db.models import F
        avvik = (VaktArkiv.objects.filter(vakt__isnull=False)
                 .exclude(year_snapshot=F('vakt__year'))
                 .count())
        if avvik:
            self._feil(f'{avvik} arkiv der year_snapshot ikke stemmer med '
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

        # Forhåndssjekken for (vakt, nummer)-kollisjoner er fjernet:
        # sperrene er databasekrav siden deploy 2, og en sjekk som aldri kan
        # finne noe er verre enn ingen.

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
            self.stdout.write(self.style.ERROR(f'\n{self.funn} funn.'))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS('\nIngen funn.'))
