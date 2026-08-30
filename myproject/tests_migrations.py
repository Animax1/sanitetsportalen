"""Vokter at modellene og migrasjonshistorikken ikke driver fra hverandre.

Fra Django 5-oppgraderingen til 23. aug. 2026 foreslo `makemigrations` to
migrasjoner ved hver eneste kjøring — en `AlterField` på `is_superuser` og en
omdøping av en indeks i `audit`. Begge ble bevisst latt ligge, og disiplinen
«husk å strippe det Django foreslår» bodde i en docstring og i hodet til den
som deployet.

Det holdt ikke. 13. august 2026 ble indeks-omdøpingen generert og pushet, og
tok ned produksjon i 30 minutter: release-fasen kjører `migrate`, så en
migrasjon som ikke kan kjøre crash-looper containeren.

Denne testen flytter disiplinen fra hukommelse til testsuite. Er det avvik
mellom modellene og migrasjonene, feiler den her — ikke i release-fasen.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class MigrasjonerErISyncTests(TestCase):

    def test_ingen_uskrevne_migrasjoner(self):
        """`makemigrations --check` skal være ren.

        Feiler denne, har noen endret en modell uten å lage migrasjonen — eller
        et avvik mellom Djangos tilstand og databasen har oppstått på nytt.
        Begge deler skal håndteres bevisst, ikke oppdages av en crash-loop i
        produksjon.

        **Ikke bare kjør `makemigrations` for å gjøre den grønn.** Les hva
        Django foreslår først, og verifiser med `sqlmigrate` hva den vil gjøre
        mot databasen. Historikken i dette prosjektet stemmer ikke automatisk
        med prod — se docstringene i `audit/0004` og `accounts/0009`.
        """
        ut = StringIO()
        try:
            call_command('makemigrations', '--check', '--dry-run',
                         stdout=ut, stderr=ut, verbosity=1)
        except SystemExit as exc:
            self.fail(
                'makemigrations --check fant endringer som mangler migrasjon:\n'
                + ut.getvalue()
                + '\nLes forslaget og kjør sqlmigrate før du genererer noe.'
                + f'\n(exit={exc.code})'
            )


class DataOgSkjemaISammeTransaksjonTests(TestCase):
    """En migrasjon som først skriver rader og deretter endrer skjema, må
    tømme PostgreSQLs triggerkø — ellers kræsjer deployen.

    **Dette tok ned deployen 30. aug. 2026.** `vaktliste.0007` seedet
    ressursgrupper, flyttet rollene og pekte om vaktpostene, og endret så
    kolonnene til NOT NULL. Djangos fremmednøkler er `DEFERRABLE INITIALLY
    DEFERRED`, så hver skriving legger en triggerhendelse i kø som først fyres
    ved commit — og migrasjonen er én transaksjon. PostgreSQL svarte::

        cannot ALTER TABLE "vaktliste_ressursrolle" because it has pending
        trigger events

    **Hele testsuiten var grønn.** SQLite har ingen utsatte triggere, så
    dev-basen kan ikke si noe om denne feilklassen i det hele tatt — den
    finnes bare i prod, og viser seg som en container i crash-loop. Testen
    flytter derfor regelen fra «husk det» til suiten, slik
    `MigrasjonerErISyncTests` over gjorde med `makemigrations --check`.

    **Regelen er bevisst grov.** Hva et `RunPython`-steg faktisk skriver, kan
    ikke leses ut av operasjonslista — så testen flagger *enhver* skriving
    fulgt av en skjemaendring, ikke bare de som treffer samme tabell. Prisen
    er `KJENTE_UNNTAK`; alternativet var en regel som ikke fanget 0007.

    **Og den har en grense det er verdt å kjenne.** Testen ser at kallet
    *finnes* i fila, ikke at det faktisk kjøres på veien gjennom. Fjernes
    kallstedet mens hjelperen blir stående, går testen grønn — det ble prøvd
    ved mutasjonstesting, og den overlevde. Å lukke det hullet krever å kjøre
    migrasjonene mot en ekte PostgreSQL med rader i, altså det TODO kaller
    «kjør suiten mot PostgreSQL». Til da fanger denne det som faktisk skjedde:
    at kallet aldri ble skrevet.
    """

    #: Operasjoner som lager eller fjerner en hel tabell. Trygge: en tabell
    #: som nettopp ble laget har ingen hendelser i køen.
    TRYGGE = {'CreateModel', 'DeleteModel'}
    #: Skrivende operasjoner — de som fyller køen.
    SKRIVENDE = {'RunPython', 'RunSQL'}

    #: Migrasjoner som har mønsteret, men som er kjørt før regelen fantes.
    #:
    #: **De er verifisert, ikke antatt.** To ting gjør dem ufarlige: de er
    #: allerede anvendt i produksjon, og en anvendt migrasjon kjøres aldri
    #: igjen der — og hele historikken er kjørt fra null mot PostgreSQL
    #: 30. aug. 2026 uten å felle noen av dem, fordi dataskrittene ikke
    #: skriver noe på en tom base og køen dermed er tom.
    #:
    #: Lista skal ikke vokse. En ny migrasjon som havner her, er en som skal
    #: rettes — ikke føres opp.
    KJENTE_UNNTAK = {
        'accounts.0003_email_optional',
        'accounts.0013_krymp_role',
        'contenttypes.0002_remove_content_type_name',   # Djangos egen
        'oppdrag.0003_oppdragsnummer_og_arkivering',
        'oppdrag.0007_vakt_er_fasit',
        'patients.0002_behandler_and_year',
        'patients.0012_vaktarkiv_importert_av_navn',
        'patients.0016_vakt_er_fasit',
    }

    def _migrasjoner(self):
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        return loader.disk_migrations

    @staticmethod
    def _kilde(app, navn):
        """Kildekoden til migrasjonsfila, lest fra disk.

        Modulstien slås opp gjennom `MigrationLoader`, ikke gjettes av
        app-etiketten: `contenttypes` bor i `django.contrib.contenttypes`, og
        `f'{app}.migrations'` finnes ikke for noen av bidrags-appene.
        """
        import importlib
        from pathlib import Path
        from django.db.migrations.loader import MigrationLoader
        pakke, _ = MigrationLoader.migrations_module(app)
        modul = importlib.import_module(f'{pakke}.{navn}')
        return Path(modul.__file__).read_text(encoding='utf-8')

    @classmethod
    def _toemmer_koen(cls, app, navn):
        """True hvis migrasjonen faktisk *kjører* `SET CONSTRAINTS ALL
        IMMEDIATE` — ikke bare nevner den.

        **Et rent tekstsøk holdt ikke.** Mutasjonstesting 30. aug. 2026:
        fjernet man kallet fra `vaktliste.0007` men lot docstringen som
        forklarer regelen stå, forble testen grønn. En migrasjon som *omtaler*
        sperren er ikke en migrasjon som har den, og forskjellen er hele
        deployen. Derfor AST: strengen må stå som argument i et kall.
        """
        import ast
        try:
            tre = ast.parse(cls._kilde(app, navn))
        except SyntaxError:                      # pragma: no cover
            return False
        for node in ast.walk(tre):
            if not isinstance(node, ast.Call):
                continue
            for arg in node.args:
                if (isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and 'SET CONSTRAINTS ALL IMMEDIATE' in arg.value):
                    return True
        return False

    def _mistenkelige(self):
        """(app.navn, operasjonene som kommer etter skrivingen)."""
        ut = []
        for (app, navn), migrasjon in sorted(self._migrasjoner().items()):
            ops = list(migrasjon.operations)
            skrivende = [i for i, op in enumerate(ops)
                         if type(op).__name__ in self.SKRIVENDE]
            if not skrivende:
                continue

            etterpaa = {
                type(op).__name__ for op in ops[min(skrivende) + 1:]
                if getattr(op, 'reduces_to_sql', False)
                and type(op).__name__ not in self.TRYGGE | self.SKRIVENDE
            }
            if etterpaa:
                ut.append((f'{app}.{navn}', sorted(etterpaa)))
        return ut

    def test_ingen_migrasjon_endrer_skjema_etter_aa_ha_skrevet_rader(self):
        farlige = []
        for navn, etterpaa in self._mistenkelige():
            if navn in self.KJENTE_UNNTAK:
                continue
            app, kortnavn = navn.split('.', 1)
            migrasjon = self._migrasjoner()[(app, kortnavn)]
            if not getattr(migrasjon, 'atomic', True):
                continue                       # kjører uten transaksjon
            if self._toemmer_koen(app, kortnavn):
                continue                       # tømmer køen selv
            farlige.append(f'{navn}: {", ".join(etterpaa)}')

        self.assertEqual(farlige, [], (
            'Disse migrasjonene skriver rader og endrer skjema i samme '
            'transaksjon:\n  ' + '\n  '.join(farlige)
            + '\n\nPå PostgreSQL gir det «cannot ALTER TABLE … because it has '
              'pending trigger events», og deployen crash-looper. SQLite '
              'merker ingenting, så testsuiten er grønn uansett.\n'
              'Velg én: kall SET CONSTRAINTS ALL IMMEDIATE etter skrivingen '
              '(se vaktliste/migrations/0007), sett atomic = False, eller '
              'del migrasjonen i to.'))

    def test_unntakslista_er_ikke_blitt_en_soppelbotte(self):
        """Hvert unntak må fortsatt ha mønsteret. Blir en migrasjon rettet
        eller fjernet, skal navnet ut av lista — ellers vokser den til et sted
        man legger ting for å slippe unna testen."""
        funnet = {navn for navn, _ in self._mistenkelige()}
        forsvunnet = self.KJENTE_UNNTAK - funnet
        self.assertEqual(forsvunnet, set(), (
            f'Disse står i KJENTE_UNNTAK uten å ha mønsteret lenger: '
            f'{sorted(forsvunnet)}. Fjern dem fra lista.'))

    def test_regelen_finner_faktisk_migrasjonene(self):
        """Grunnlaget for testen over: finner den ingen migrasjoner, måler den
        ingenting og går grønn på tom luft."""
        self.assertGreater(len(self._migrasjoner()), 20)
