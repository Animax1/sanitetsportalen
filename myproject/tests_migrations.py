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
