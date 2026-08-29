"""Statistikkregisteret (fase 6 av oppdragsmodulen).

Registeret erstattet den direkte importen fra statistikkappen til
``patients.services``. Testene her dekker det bytte faktisk endret:

- begge modulene melder seg inn selv, fra ``apps.ready()``
- statistikkappen navngir ingen kildemodul
- en handler uten slug avvises, og rekkefølgen er sortert, ikke tilfeldig
- basisklassens ``arkiv_full_stats`` svarer «finnes ikke», ikke krasj
"""
import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from core.stats import BaseStatistikkHandler, all_handlers, get_handler


class RegisterInnholdTests(TestCase):
    """Modulene melder seg inn selv — ingen liste noe sted som må vedlikeholdes."""

    def test_begge_modulene_er_registrert(self):
        slugs = [h.slug for h in all_handlers()]
        self.assertIn('patients', slugs)
        self.assertIn('oppdrag', slugs)

    def test_slug_matcher_modulregistryet(self):
        """Slug-en er både registernøkkel og modulen tilgangen sjekkes mot.

        Er de to ulike, sjekker statistikkappen tilgang mot en modul som ikke
        finnes — og `har_tilgang` svarer False på ukjent slug. Kilden ville
        vært usynlig for alle, uten at noe feilet.
        """
        from core.modules import get_module

        for handler in all_handlers():
            with self.subTest(slug=handler.slug):
                self.assertIsNotNone(
                    get_module(handler.slug),
                    f'«{handler.slug}» finnes ikke i core.modules')

    def test_rekkefolgen_er_sortert_ikke_innsettingsrekkefolge(self):
        """Rekkefølgen her blir fanerekkefølgen på siden."""
        handlere = all_handlers()
        self.assertEqual(
            [h.slug for h in handlere],
            [h.slug for h in sorted(handlere, key=lambda h: (h.order, h.slug))])
        self.assertEqual(handlere[0].slug, 'patients')

    def test_alle_handlere_har_visningsnavn(self):
        for handler in all_handlers():
            with self.subTest(slug=handler.slug):
                self.assertTrue(handler.display_name,
                                'display_name er fanenavnet i grensesnittet')


class RegisterKontraktTests(SimpleTestCase):
    def test_handler_uten_slug_avvises(self):
        from core.stats import _Registry

        class UtenSlug(BaseStatistikkHandler):
            pass

        with self.assertRaises(ValueError):
            _Registry().register(UtenSlug())

    def test_ukjent_slug_gir_none(self):
        self.assertIsNone(get_handler('finnes-ikke'))

    def test_full_stats_maa_implementeres(self):
        """En handler som glemmer tallene skal si fra, ikke svare tomt."""
        with self.assertRaises(NotImplementedError):
            BaseStatistikkHandler().full_stats(vakt=None)

    def test_arkiv_stats_er_valgfri_og_svarer_ingenting(self):
        """Oppdrag arkiverer først i fase 7 — fram til da er svaret «finnes ikke»."""
        self.assertIsNone(BaseStatistikkHandler().arkiv_full_stats(1))
        self.assertIsNone(get_handler('oppdrag').arkiv_full_stats(1))


class StatistikkappenNavngirIngenKilde(SimpleTestCase):
    """Akseptansekriteriet for fase 6, lest ut av kilden.

    Statistikkappen skal ikke importere fra en kildemodul for å hente tall.
    Testen leser importene med AST framfor å søke i tekst, slik at omtale i
    docstrings og kommentarer — som det er en del av i den fila — ikke gir
    falske treff.
    """

    #: `hent_aktiv_vakt` er portalens scope, ikke en kildes tall. `Vakt` bor i
    #: `core`, men funksjonen ble liggende i pasientmodulen fordi
    #: `AppSetting`-pekeren gjør det. Oppdragsmodulen importerer den fra samme
    #: sted. Å flytte den hører til den ryddejobben, ikke til registeret.
    TILLATT = {('patients.services', 'hent_aktiv_vakt')}

    def test_ingen_import_av_kildemodulenes_tall(self):
        kilde = Path(settings.BASE_DIR, 'statistikk', 'views.py')
        tre = ast.parse(kilde.read_text(encoding='utf-8'), filename=str(kilde))

        funn = []
        for node in ast.walk(tre):
            moduler = []
            if isinstance(node, ast.ImportFrom) and node.module:
                moduler = [(node.module, alias.name) for alias in node.names]
            elif isinstance(node, ast.Import):
                moduler = [(alias.name, '') for alias in node.names]
            for modul, navn in moduler:
                rot = modul.split('.')[0]
                if rot in ('patients', 'oppdrag') and (modul, navn) not in self.TILLATT:
                    funn.append(f'{modul}.{navn}')

        self.assertEqual(funn, [], (
            'statistikk/views.py importerer fra en kildemodul:\n  '
            + '\n  '.join(funn)
            + '\n\nTall hentes gjennom core.stats-registeret. Var importen '
              'nødvendig, hører den til i modulens egen handler.'
        ))
