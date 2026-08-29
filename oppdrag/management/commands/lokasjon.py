"""Vedlikehold lokasjonslista fra kommandolinjen.

Lokasjonene er stedene på *dette* arrangementet, og skal kunne endres uten
deploy. Den permanente flaten er en admin-side i oppdragsmodulen, og den
kommer i fase 3 sammen med sentralbordet.

**Hvorfor ikke en side allerede nå:** modulen har ingen URL ennå, med vilje —
et modulkort som fører til 404 er en knapp som fører til en vegg. En
admin-side uten vei inn er den samme feilen med et ekstra steg; portalen har
allerede hatt én slik, og den ble oppdaget ved at noen måtte skrive URL-en for
hånd.

Kommandoen følger `appsetting`-presedensen: den dekker behovet fram til flaten
finnes, og gjør staging mulig å fylle med testdata før fase 3 skrives.

Bruk::

    python manage.py lokasjon --list
    python manage.py lokasjon --legg-til "Hovedscene"
    python manage.py lokasjon --legg-til "Inngang Nord" --rekkefolge 10
    python manage.py lokasjon --deaktiver "Hovedscene"
    python manage.py lokasjon --aktiver "Hovedscene"
    python manage.py lokasjon --gi-nytt-navn "Hovedscene" "Scene 1"
"""
from django.core.management.base import BaseCommand, CommandError

from oppdrag.models import Lokasjon


class Command(BaseCommand):
    help = 'Vis eller endre lokasjonslista for oppdragsmodulen.'

    def add_arguments(self, parser):
        gruppe = parser.add_mutually_exclusive_group(required=True)
        gruppe.add_argument('--list', action='store_true',
                            help='Vis alle lokasjoner, aktive og inaktive.')
        gruppe.add_argument('--legg-til', metavar='NAVN',
                            help='Opprett en ny lokasjon.')
        gruppe.add_argument('--deaktiver', metavar='NAVN',
                            help='Skjul lokasjonen i nedtrekkslista.')
        gruppe.add_argument('--aktiver', metavar='NAVN',
                            help='Vis lokasjonen i nedtrekkslista igjen.')
        gruppe.add_argument('--gi-nytt-navn', nargs=2, metavar=('FRA', 'TIL'),
                            help='Endre navnet på en lokasjon.')
        parser.add_argument('--rekkefolge', type=int, default=None,
                            help='Sorteringsnøkkel. Lavere kommer først.')

    def handle(self, *args, **opts):
        if opts['list']:
            return self._list()
        if opts['legg_til']:
            return self._legg_til(opts['legg_til'], opts['rekkefolge'])
        if opts['deaktiver']:
            return self._sett_aktiv(opts['deaktiver'], False)
        if opts['aktiver']:
            return self._sett_aktiv(opts['aktiver'], True)
        if opts['gi_nytt_navn']:
            return self._gi_nytt_navn(*opts['gi_nytt_navn'])

    def _hent(self, navn):
        try:
            return Lokasjon.objects.get(navn=navn.strip())
        except Lokasjon.DoesNotExist:
            raise CommandError(f'Ingen lokasjon heter «{navn}».')

    def _list(self):
        rader = list(Lokasjon.objects.all())
        if not rader:
            self.stdout.write(self.style.WARNING(
                'Ingen lokasjoner. Legg til med --legg-til "Navn".'))
            return
        self.stdout.write(f'  {"rekkefølge":>10}  {"status":8} navn')
        self.stdout.write('  ' + '─' * 50)
        for lok in rader:
            status = 'aktiv' if lok.er_aktiv else 'inaktiv'
            self.stdout.write(f'  {lok.rekkefolge:>10}  {status:8} {lok.navn}')

    def _legg_til(self, navn, rekkefolge):
        navn = navn.strip()
        if not navn:
            raise CommandError('Navnet kan ikke være tomt.')
        if Lokasjon.objects.filter(navn=navn).exists():
            raise CommandError(f'«{navn}» finnes allerede.')
        lok = Lokasjon.objects.create(
            navn=navn,
            **({'rekkefolge': rekkefolge} if rekkefolge is not None else {}),
        )
        self.stdout.write(self.style.SUCCESS(
            f'Opprettet «{lok.navn}» (rekkefølge {lok.rekkefolge}).'))

    def _sett_aktiv(self, navn, aktiv):
        """Deaktivering, ikke sletting.

        En lokasjon som er brukt på et oppdrag kan ikke forsvinne uten å ta
        historikken med seg — FK-en er `PROTECT`. Deaktivering fjerner den fra
        nedtrekkslista og lar radene bestå.
        """
        lok = self._hent(navn)
        lok.er_aktiv = aktiv
        lok.save(update_fields=['er_aktiv', 'updated_at'])
        ord_ = 'aktivert' if aktiv else 'deaktivert'
        self.stdout.write(self.style.SUCCESS(f'«{lok.navn}» er {ord_}.'))

    def _gi_nytt_navn(self, fra, til):
        """Navnet endres på raden — oppdragene følger med.

        Det er med vilje: et sted som skifter navn er fortsatt samme sted, og
        et oppdrag skal vise stedet slik det heter nå. Skal det gamle navnet
        bevares på gamle oppdrag, er det en ny lokasjon, ikke et nytt navn.
        """
        lok = self._hent(fra)
        til = til.strip()
        if not til:
            raise CommandError('Det nye navnet kan ikke være tomt.')
        if Lokasjon.objects.filter(navn=til).exclude(pk=lok.pk).exists():
            raise CommandError(f'«{til}» finnes allerede.')
        gammelt = lok.navn
        lok.navn = til
        lok.save(update_fields=['navn', 'updated_at'])
        antall = lok.oppdrag.count()
        self.stdout.write(self.style.SUCCESS(
            f'«{gammelt}» heter nå «{til}». {antall} oppdrag følger med.'))
