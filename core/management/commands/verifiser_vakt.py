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

from core.sortering import Norsk
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
        Vaktportal = apps.get_model('core', 'Vaktportal')
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

        # ── Aktiv vakt per portal (17. okt. 2026) ────────────────────────
        # `er_aktiv` er fasit, og indeksen `en_aktiv_vakt_per_portal` sier at
        # det er høyst én per portal. Det som gjenstår å sjekke er vakter uten
        # portal — de kommer fra en backup tatt før portalene, og er usynlige
        # for `hent_aktiv_vakt` til de tas inn.
        uten_portal = Vakt.objects.filter(portal__isnull=True).count()
        if uten_portal:
            self._feil(f'{uten_portal} vakt(er) uten portal. Gjenåpne dem fra '
                       f'vaktsiden for å ta dem inn i en portal.')
        for portal in Vaktportal.objects.order_by(Norsk('navn')):
            aktiv = Vakt.objects.filter(portal=portal, er_aktiv=True).first()
            if aktiv is None:
                self.stdout.write(f'  Info: «{portal.navn}» har ingen aktiv vakt. '
                                  f'Settes ved første registrering (lat opprettelse).')
            else:
                self.stdout.write(f'  Aktiv vakt i «{portal.navn}»: «{aktiv.navn}» '
                                  f'(year={aktiv.year}).')

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
