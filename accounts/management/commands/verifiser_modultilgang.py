"""Les-only kontroll av ``ModulTilgang`` mot ``role``.

Kjøres mot **prod** mellom deploy 1 og deploy 2, som §10.1 i
``docs/BESLUTNING_ROLLEMODELLEN.md`` krever. Kommandoen skriver ingenting.

To spørsmål den svarer på:

1. **Hvor mange kontoer hadde en tilgang de ikke var ment å ha?**
   Kontoer med ``role >= read_write`` men ``kan_redigere_pasienter=False``
   kunne nå ``/pasienter/`` via URL-en likevel — flagget stengte aldri noe
   (§2.1). Backfillen ga dem en rad som *bekrefter* tilgangen de faktisk
   hadde, med vilje: en migrasjon som stille trekker tilbake tilgang oppdager
   du midt i en vakt. Tallet her sier hvor mange du bør stramme inn for hånd.

2. **Stemmer matrisen med det backfillen ga?** Avvik er ikke feil i seg selv
   — de er endringer noen har gjort etterpå, som er hele poenget med
   matrisen. Men de skal være gjenkjennelige. Er de ikke det, er det verdt å
   vite *før* ``role`` krymper og fasiten forsvinner.

Deploy 2 kan ikke kjøres før dette er sett over: ``lead_view → bruker`` er
ikke rullbar uten ``ModulTilgang``.
"""
from django.core.management.base import BaseCommand

from accounts.models import CustomUser, ModulTilgang

# Samme kartlegging som accounts/migrations/0012_fyll_modultilgang.py.
BACKFILL = {
    'read_only':  {('patients', 'les')},
    'read_write': {('patients', 'skriv_full')},
    'lead_view':  {('patients', 'les'), ('statistikk', 'les')},
    'lead':       {('patients', 'skriv_full'), ('statistikk', 'les')},
    'admin':      set(),
}

# Rollene §10.1 spør etter. **Admin er utelatt med vilje**, selv om notatet
# skriver «role >= read_write»: global admin har alltid hatt bypass i
# `is_visible_for`, så flagget var aldri en begrensning for dem — de var *ment*
# å ha tilgangen. Tas de med, teller tallet kontoer som aldri var et problem,
# og signalet drukner.
SKRIVEROLLER = ('read_write', 'lead')


class Command(BaseCommand):
    help = 'Kontroller ModulTilgang mot role. Skriver ingenting (§10.1).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--vis-alle', action='store_true',
            help='List hver konto, ikke bare avvikene.',
        )
        parser.add_argument(
            '--forhandsvis', action='store_true',
            help=('Vis hva backfillen VIL gi, uten å lese ModulTilgang. '
                  'Kjøres FØR deploy 1, når tabellen ikke finnes ennå.'),
        )

    def _forhandsvis(self):
        """Hva backfillen vil produsere, lest fra `role` alene.

        Rører ikke ``ModulTilgang`` — tabellen finnes ikke før migrasjonen har
        kjørt, og hele poenget er å kunne se resultatet *før* man deployer.

        **Merk hva den viser om flagget.** Backfillen utleder fra `role` og
        ignorerer `kan_redigere_pasienter` med vilje (§8.1). Har noen redusert
        en konto ved å fjerne flagget i stedet for å endre rollen, har det
        ikke hatt noen virkning — flagget stengte aldri et endepunkt — og
        backfillen vil gi kontoen det rollen tilsier. Kolonnen under gjør den
        forskjellen synlig før den blir en overraskelse.
        """
        brukere = list(CustomUser.objects.all().order_by('username'))
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Forhåndsvisning — hva backfillen vil gi hver konto'))
        self.stdout.write('')
        self.stdout.write(
            f'  {"konto":24} {"rolle":11} {"flagg":6} → modultilgang')
        self.stdout.write('  ' + '─' * 70)

        overraskelser = []
        for b in brukere:
            rader = BACKFILL.get(b.role, set())
            vist = ', '.join(f'{s}:{n}' for s, n in sorted(rader))
            if b.role == 'admin':
                vist = '(global admin — ingen rader)'
            flagg = 'ja' if b.kan_redigere_pasienter else 'nei'
            self.stdout.write(f'  {b.username:24} {b.role:11} {flagg:6} → {vist}')

            skriver = any(n.startswith('skriv') for _, n in rader)
            if skriver and not b.kan_redigere_pasienter:
                overraskelser.append(b)

        if overraskelser:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Kontoer som får SKRIVETILGANG selv om flagget er av:'))
            for b in overraskelser:
                self.stdout.write(self.style.WARNING(
                    f'  {b.username} ({b.role})'))
            self.stdout.write(
                '  Flagget har aldri stengt noe (§2.1), så disse har skrivetilgang\n'
                '  i prod allerede — backfillen bekrefter den, den gir den ikke.\n'
                '  Skal de ha mindre, endre `role` FØR deploy, eller sett nivået i\n'
                '  matrisen ETTER. Ikke fjern flagget: det gjør ingenting.')

        self.stdout.write('')
        self.stdout.write(
            'Ingenting er skrevet. Kjør uten --forhandsvis etter deploy 1 for å\n'
            'kontrollere at resultatet ble som vist over.')

    def handle(self, *args, **opts):
        if opts['forhandsvis']:
            return self._forhandsvis()
        brukere = list(
            CustomUser.objects.all().order_by('username').prefetch_related('modultilganger')
        )
        if not brukere:
            self.stdout.write(self.style.WARNING('Ingen brukere i databasen.'))
            return

        uten_rader, avvik, spoekelser = [], [], []
        for b in brukere:
            faktisk = {(t.modul_slug, t.nivaa) for t in b.modultilganger.all()}
            forventet = BACKFILL.get(b.role, set())

            if b.role != 'admin' and not faktisk:
                uten_rader.append(b)
            if faktisk != forventet:
                avvik.append((b, forventet, faktisk))
            if b.role not in BACKFILL:
                spoekelser.append(b)

            if opts['vis_alle']:
                rader = ', '.join(f'{s}:{n}' for s, n in sorted(faktisk)) or '(ingen)'
                self.stdout.write(f'  {b.username:24} {b.role:11} {rader}')

        # ── §10.1: kontoene som hadde tilgang de ikke var ment å ha ──────
        antall = CustomUser.objects.filter(
            role__in=SKRIVEROLLER, kan_redigere_pasienter=False).count()
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            '§10.1 — kontoer med skrivetilgang, men kan_redigere_pasienter=False'
            ' (admin utelatt: de hadde bypass uansett)'))
        self.stdout.write(f'  Antall: {antall} av {len(brukere)}')
        if antall:
            navn = CustomUser.objects.filter(
                role__in=SKRIVEROLLER, kan_redigere_pasienter=False
            ).order_by('username').values_list('username', 'role')
            for n, r in navn:
                self.stdout.write(f'    {n} ({r})')
            self.stdout.write(
                '  Disse kunne nå modulen via URL-en før håndhevelsen, og har nå\n'
                '  en rad som bekrefter det. Vurder om de skal beholde tilgangen.')

        # ── Kontoer som ikke ser noen modul ─────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Kontoer uten en eneste ModulTilgang-rad (ser en tom portal)'))
        if uten_rader:
            for b in uten_rader:
                self.stdout.write(self.style.WARNING(f'  {b.username} ({b.role})'))
            self.stdout.write(
                '  Global admin trenger ingen rader; disse er ikke admin.\n'
                '  Sannsynligvis opprettet etter migrasjonen, uten at matrisen ble satt.')
        else:
            self.stdout.write('  Ingen.')

        # ── Avvik fra backfillen ────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Avvik fra det backfillen ga (endringer gjort etterpå)'))
        if avvik:
            for b, forventet, faktisk in avvik:
                f = ', '.join(f'{s}:{n}' for s, n in sorted(forventet)) or '(ingen)'
                a = ', '.join(f'{s}:{n}' for s, n in sorted(faktisk)) or '(ingen)'
                self.stdout.write(f'  {b.username} ({b.role})')
                self.stdout.write(f'      backfill ville gitt: {f}')
                self.stdout.write(f'      har nå:              {a}')
            self.stdout.write(
                '  Avvik er ikke feil — matrisen er ment å brukes. Men de bør være\n'
                '  gjenkjennelige, for etter deploy 2 finnes ikke fasiten lenger.')
        else:
            self.stdout.write('  Ingen. Matrisen er urørt siden backfillen.')

        if spoekelser:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                'Kontoer med en rolle kartleggingen ikke kjenner:'))
            for b in spoekelser:
                self.stdout.write(self.style.ERROR(f'  {b.username} ({b.role})'))

        self.stdout.write('')
        self.stdout.write(
            'Kommandoen har ikke skrevet noe. Deploy 2 krymper `role`, og da er\n'
            'ModulTilgang eneste fasit — se §8 i beslutningsnotatet.')
