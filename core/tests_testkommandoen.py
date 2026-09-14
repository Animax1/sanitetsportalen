"""Den dokumenterte testkommandoen må dekke alle testene (14. sep. 2026).

**Hvorfor dette er en test og ikke en kommentar.** Kommandoen i `CLAUDE.md`
utelot appen `myproject` — 32 tester på databasevalg, cache, `_env_bool`,
statiske filer og migrasjoner. Altså vaktene rundt «`DATABASE_URL` må være
PostgreSQL når `RAILWAY_ENVIRONMENT` er satt» og rundt den `_env_bool` som
hadde rate-limitingen av i prod til 13. sep. Den som fulgte dokumentasjonen
kjørte dem aldri, og ingenting sa fra.

Feilen ble oppdaget ved et tilfelle: testtallet stemte ikke mot forrige
kjøring. Det er ikke en mekanisme, det er flaks — og den flaksen kan man ikke
planlegge to ganger.

Det var samme dag som `SignalerFyrerIkkeUnderLoaddataTests` viste seg å lete i
en håndskrevet liste over tre apper, og dermed ikke ville sett `core/signals.py`
den dagen den ble skrevet. To ganger samme lærdom: **en liste over hvor man
skal lete er alltid et sted færre enn der koden er.**
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CLAUDE_MD = Path(settings.BASE_DIR) / 'CLAUDE.md'

#: Mapper som har `test*.py` uten at Django-kjøreren skal ta dem.
#: Unntaksliste med begrunnelse, ikke en tillatelse.
IKKE_TESTPAKKER: frozenset[str] = frozenset({
    '.venv', 'node_modules', 'staticfiles', 'docs', 'scripts',
})


def _pakker_med_tester() -> set[str]:
    """Toppnivåpakker som Django-kjøreren ville funnet tester i.

    Kravet er å være en importerbar pakke (`__init__.py`) med minst én
    `test*.py` — det er nøyaktig det kjøreren leter etter når den får et
    app-navn som etikett.
    """
    ut = set()
    for sti in Path(settings.BASE_DIR).iterdir():
        if not sti.is_dir() or sti.name in IKKE_TESTPAKKER or sti.name.startswith('.'):
            continue
        if not (sti / '__init__.py').exists():
            continue
        if any(sti.glob('test*.py')) or any(sti.glob('*/test*.py')):
            ut.add(sti.name)
    return ut


def _dokumentert_kommando() -> list[str]:
    """Etikettene i `python manage.py test …` i CLAUDE.md, hele suiten."""
    tekst = CLAUDE_MD.read_text(encoding='utf-8')
    treff = re.findall(r'^python manage\.py test ([a-z_ ]+?)(?: -v \d)?$',
                       tekst, re.M)
    # Den lengste linja er hele suiten; de andre er enkelt-test-eksempler.
    if not treff:
        return []
    return max(treff, key=lambda t: len(t.split())).split()


class TestkommandoenDekkerAltTests(SimpleTestCase):

    def test_kommandoen_finnes_i_claude_md(self):
        """Finner ikke regexen kommandoen, måler resten av fila ingenting —
        og går grønn mens den gjør det."""
        self.assertNotEqual(
            _dokumentert_kommando(), [],
            'fant ingen «python manage.py test …»-linje i CLAUDE.md — enten er '
            'kommandoen borte, eller så leter regexen her feil')

    def test_vi_finner_flere_pakker_med_tester(self):
        """Samme sperrehake fra den andre siden: finner oppdagelsen nesten
        ingenting, er den i stykker og testen under blir meningsløs."""
        self.assertGreaterEqual(len(_pakker_med_tester()), 7)

    def test_hver_pakke_med_tester_staar_i_kommandoen(self):
        dokumentert = set(_dokumentert_kommando())
        mangler = sorted(_pakker_med_tester() - dokumentert)
        self.assertEqual(
            mangler, [],
            'Disse pakkene har tester som den dokumenterte kommandoen i '
            'CLAUDE.md ikke kjører:\n  ' + '\n  '.join(mangler)
            + '\n\nLegg dem til i kommandoen under «Tester – hele suiten».')

    def test_kommandoen_navngir_ingenting_som_ikke_finnes(self):
        """Den andre retningen. En etikett som ikke finnes får kjøringen til å
        stoppe med «No installed app with label», altså hele suiten rød —
        men først hos den som prøver, ikke her."""
        ukjente = sorted(set(_dokumentert_kommando()) - _pakker_med_tester())
        self.assertEqual(
            ukjente, [],
            'CLAUDE.md navngir pakker som ikke har tester: ' + ', '.join(ukjente))
