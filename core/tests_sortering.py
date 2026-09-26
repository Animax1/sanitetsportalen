"""Norsk alfabetisk rekkefølge — regelen og at den brukes (26. sep. 2026).

Se `core/sortering.py`. Tre ting prøves:

1. **Nøkkelen er norsk**: Æ Ø Å sist og i den rekkefølgen, «aa» er Å, store og
   små bokstaver likt. Og den er enig med ICU (`nb-NO-x-icu`) — prøvd mot ekte
   PostgreSQL i CI, der `norsk_nokkel` og basen sorterer samme navn.
2. **Hver liste bruker den**: ingen `Meta.ordering` eller `order_by(...)` på et
   navnefelt uten `Norsk`. En håndholdt liste over steder ble funnet ufullstendig
   samme dag — `order_by('-is_active', 'name')` slapp forbi et søk som bare så
   etter ett argument. Derfor utledes stedene av modellene og av kildekoden.
3. **Rekkefølgereglene står**: lagleder før hospitant, og tid før rolle. `Norsk`
   skal bare avgjøre uavgjort.
"""
from __future__ import annotations

import ast
import unittest
from datetime import timedelta
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.db.models import F
from django.db.models.expressions import OrderBy
from django.db.models.functions import Lower
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from core.sortering import Norsk, norsk_nokkel, norsk_sql, norsk_tilgjengelig

NAVN = ['Ålesund', 'bergen', 'Aasen', 'Zeta', 'Ørsta', 'Ærø', 'Haugesund', 'Andøy',
        'Oslo', 'Bergen', 'Émile', 'Øyvind Ødegård', 'Korps 2', 'Korps 10']
#: ICU nb og nettleserens `localeCompare(…, 'nb')` ga denne 26. sep. 2026.
NORSK = ['Andøy', 'bergen', 'Bergen', 'Émile', 'Haugesund', 'Korps 10', 'Korps 2', 'Oslo',
         'Zeta', 'Ærø', 'Ørsta', 'Øyvind Ødegård', 'Ålesund', 'Aasen']


class NokkelenTests(SimpleTestCase):

    def test_norsk_rekkefolge(self):
        self.assertEqual(sorted(NAVN, key=norsk_nokkel), NORSK)

    def test_ae_oe_aa_sist_og_i_riktig_rekkefolge(self):
        self.assertEqual(sorted(['å', 'ø', 'æ', 'z', 'a'], key=norsk_nokkel), ['a', 'z', 'æ', 'ø', 'å'])

    def test_aa_er_aa(self):
        # «Aasen» leses «Åsen»: etter «Azur» og etter «Åse», som er kortere.
        self.assertEqual(sorted(['Aasen', 'Azur', 'Åse'], key=norsk_nokkel), ['Azur', 'Åse', 'Aasen'])
        self.assertEqual(sorted(['Aasen', 'Ålesund'], key=norsk_nokkel), ['Ålesund', 'Aasen'])

    def test_store_og_smaa_likt_liten_foerst_ved_likhet(self):
        self.assertEqual(sorted(['Oslo', 'bergen', 'Bergen'], key=norsk_nokkel), ['bergen', 'Bergen', 'Oslo'])

    def test_varianter_og_aksenter(self):
        self.assertEqual(sorted(['Øst', 'Ödön', 'Oslo'], key=norsk_nokkel)[0], 'Oslo', 'ö er ø')
        self.assertLess(norsk_nokkel('Émile'), norsk_nokkel('Erik'), 'é er e')

    def test_none_er_tom(self):
        self.assertEqual(sorted(['b', None], key=norsk_nokkel), [None, 'b'])


class BasenSortererNorskTests(TestCase):
    """Gjennom ORM-en, på den basen testene kjører mot. SQLite prøver
    kollasjonen `norsk`; PostgreSQL i CI prøver ICU — og dermed at ICU og
    `norsk_nokkel` er enige."""

    def test_norsk_regel_finnes(self):
        self.assertTrue(norsk_tilgjengelig(connection))

    def test_korps_sorteres_norsk(self):
        from vaktliste.models import Korps
        for n in NAVN:
            Korps.objects.create(navn=n, kortnavn=n[:6])
        self.assertEqual(list(Korps.objects.values_list('navn', flat=True)), NORSK)

    def test_ra_sql_er_enig_med_nokkelen(self):
        utvalg = ' UNION ALL '.join(['SELECT %s AS n'] * len(NAVN))
        with connection.cursor() as cur:
            cur.execute(f'SELECT n FROM ({utvalg}) AS t ORDER BY {norsk_sql(connection, "n")}', NAVN)
            self.assertEqual([r[0] for r in cur.fetchall()], NORSK)

    @unittest.skipUnless(connection.vendor == 'postgresql', 'reserven finnes bare på PostgreSQL')
    def test_uten_norsk_kollasjon_faller_den_tilbake(self):
        """Mangler ICU-kollasjonen, skal listene sortere som før — ikke gi 500."""
        forrige = getattr(connection, '_norsk_kollasjon', None)
        connection._norsk_kollasjon = False
        try:
            self.assertEqual(norsk_sql(connection, 'navn'), 'LOWER(navn)')
            from vaktliste.models import Korps
            list(Korps.objects.all())
        finally:
            connection._norsk_kollasjon = forrige


# ── Regel 2: hver navnesortering bruker Norsk ────────────────────────────────

#: Unntak, med begrunnelse. Skal ikke vokse uten en god grunn.
UNNTATT = {
    # Arkivraden er signert; rekkefølgen i payloaden bestemmes i
    # `oppdrag/arkiv.py`, og en endret standardorden rører ingenting der — men
    # et arkiv skal ikke endre form fordi en liste i sentralbordet gjorde det.
    ('oppdrag.ArkivertOppdrag', 'enhet_navn'),
}


def _er_navnefelt(sti: str) -> bool:
    felt = sti.lstrip('-').split('__')[-1]
    return felt in ('navn', 'name') or felt.endswith('_navn')


def _navnefelt_uten_norsk(uttrykk):
    """Feltnavnet hvis `uttrykk` sorterer et navnefelt uten `Norsk`, ellers None."""
    if isinstance(uttrykk, str):
        return uttrykk if _er_navnefelt(uttrykk) else None
    if isinstance(uttrykk, OrderBy):
        uttrykk = uttrykk.expression
    if isinstance(uttrykk, Norsk):
        return None
    if isinstance(uttrykk, (Lower, F)):
        kilde = uttrykk.source_expressions[0] if isinstance(uttrykk, Lower) else uttrykk
        navn = getattr(kilde, 'name', None)
        return navn if navn and _er_navnefelt(navn) else None
    return None


class HverNavnesorteringErNorskTests(SimpleTestCase):

    def test_meta_ordering(self):
        brudd = []
        for modell in apps.get_models():
            if not modell.__module__.split('.')[0] in _prosjektapper():
                continue
            for ledd in modell._meta.ordering or ():
                felt = _navnefelt_uten_norsk(ledd)
                navn = f'{modell._meta.app_label}.{modell.__name__}'
                if felt and (navn, felt.lstrip('-')) not in UNNTATT:
                    brudd.append(f'{navn}: {felt}')
        self.assertEqual(brudd, [], "Bruk Norsk('…') fra core.sortering")

    def test_order_by_i_koden(self):
        brudd = []
        for fil in _kildefiler():
            tre = ast.parse(fil.read_text(encoding='utf-8'))
            for node in ast.walk(tre):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == 'order_by'):
                    continue
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and _er_navnefelt(arg.value):
                        brudd.append(f'{fil.relative_to(settings.BASE_DIR)}:{node.lineno} {arg.value!r}')
                    if (isinstance(arg, ast.Call) and getattr(arg.func, 'id', None) == 'Lower'
                            and arg.args and isinstance(arg.args[0], ast.Constant)
                            and _er_navnefelt(arg.args[0].value)):
                        brudd.append(f'{fil.relative_to(settings.BASE_DIR)}:{node.lineno} Lower({arg.args[0].value!r})')
        self.assertEqual(brudd, [], "Bruk Norsk('…') fra core.sortering")

    def test_regelen_ser_det_den_skal(self):
        """Uten denne kunne `_er_navnefelt` ha sluttet å kjenne igjen noe, og
        begge testene over stått grønne på ingenting."""
        self.assertEqual(_navnefelt_uten_norsk('-name'), '-name')
        self.assertEqual(_navnefelt_uten_norsk(Lower('navn')), 'navn')
        self.assertEqual(_navnefelt_uten_norsk(F('mannskap__navn').asc()), 'mannskap__navn')
        self.assertIsNone(_navnefelt_uten_norsk(Norsk('navn').asc()))
        self.assertIsNone(_navnefelt_uten_norsk('username'), 'brukernavn er teknisk, ikke et navn')
        self.assertIsNone(_navnefelt_uten_norsk('rekkefolge'))


def _prosjektapper() -> set[str]:
    rot = Path(settings.BASE_DIR)
    return {p.parent.name for p in rot.glob('*/models.py')}


def _kildefiler():
    rot = Path(settings.BASE_DIR)
    for app in sorted(_prosjektapper()):
        for fil in (rot / app).rglob('*.py'):
            if 'migrations' in fil.parts or fil.name.startswith('tests') or fil.name == 'test_helpers.py':
                continue
            yield fil


# ── Regel 3: rekkefølgereglene står foran navnet ─────────────────────────────

class RollenFoerNavnetTests(TestCase):
    """Lagleder før lagsmedlem, uansett hva de heter — og tid før rolle."""

    def test_skiftene(self):
        from core.vakt import hent_aktiv_vakt
        from vaktliste.models import Korps, Mannskap, Ressurs, Ressursrolle, Vaktliste, Vaktpost
        from vaktliste.test_helpers import LAG, gruppe
        vl = Vaktliste.objects.create(vakt=hent_aktiv_vakt())
        g = gruppe(LAG)
        leder = Ressursrolle.objects.create(gruppe=g, navn='Lagleder', rekkefolge=1)
        medlem = Ressursrolle.objects.create(gruppe=g, navn='Lagsmedlem', rekkefolge=2)
        r = Ressurs.objects.create(vaktliste=vl, navn='Lag 1', gruppe=g)
        korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        t0 = timezone.now().replace(microsecond=0)
        rader = [('Åse', medlem, 0), ('Ærlig', medlem, 0), ('Øyvind', leder, 0), ('Anne', medlem, 8)]
        for navn, rolle, h in rader:
            m = Mannskap.objects.create(navn=navn, korps=korps)
            Vaktpost.objects.create(ressurs=r, mannskap=m, rolle=rolle,
                                    fra_tid=t0 + timedelta(hours=h), til_tid=t0 + timedelta(hours=h + 8))
        self.assertEqual([vp.mannskap.navn for vp in Vaktpost.objects.filter(ressurs=r)],
                         ['Øyvind', 'Ærlig', 'Åse', 'Anne'],
                         'lederen først selv med Ø; så Æ før Å; så senere starttid')

    def test_rollene(self):
        from vaktliste.models import Ressursrolle
        from vaktliste.test_helpers import LAG, gruppe
        g = gruppe(LAG)
        Ressursrolle.objects.create(gruppe=g, navn='Øvrig', rekkefolge=3)
        Ressursrolle.objects.create(gruppe=g, navn='Hospitant', rekkefolge=2)
        Ressursrolle.objects.create(gruppe=g, navn='Åpen leder', rekkefolge=1)
        self.assertEqual([r.navn for r in Ressursrolle.objects.filter(gruppe=g)],
                         ['Åpen leder', 'Hospitant', 'Øvrig'])


class EndepunkteneTests(TestCase):
    """Gjennom den ekte inngangen. `vaktliste/api/mannskap/` teller skift med
    `annotate(Count)`, og da dropper Django `Meta.ordering` — lista kom usortert
    fra serveren til 26. sep. 2026 uten at noe var rødt, fordi tabellen sorterer
    på nytt i nettleseren. Neste leser av endepunktet ville ikke gjort det."""

    def setUp(self):
        from accounts.models import CustomUser
        from accounts.test_helpers import gi_standardtilgang
        self.admin = CustomUser.objects.create_user(
            username='sortering_admin', password='x', role='admin', must_change_password=False)
        gi_standardtilgang(self.admin, 'admin')
        self.client.force_login(self.admin)

    def _hent(self, url):
        res = self.client.get(url, secure=True)
        self.assertEqual(res.status_code, 200, res.content[:200])
        svar = res.json()
        return svar['data'] if isinstance(svar, dict) else svar   # registrene svarer med en ren liste

    def test_mannskap(self):
        from vaktliste.models import Korps, Mannskap
        korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        for navn in ('Åse Åsen', 'Ola Olsen', 'Øyvind Ødegård', 'Anne Berg', 'Ærlig Ærdal'):
            Mannskap.objects.create(navn=navn, korps=korps)
        self.assertEqual([m['navn'] for m in self._hent('/vaktliste/api/mannskap/')['mannskap']],
                         ['Anne Berg', 'Ola Olsen', 'Ærlig Ærdal', 'Øyvind Ødegård', 'Åse Åsen'])

    def test_forstehjelpere(self):
        from patients.models import Forstehjelper
        Forstehjelper.objects.all().delete()
        for navn in ('Åse', 'Ola', 'Ærlig', 'Anne'):
            Forstehjelper.objects.create(name=navn)
        self.assertEqual([r['name'] for r in self._hent('/pasienter/api/forstehjelpere/')],
                         ['Anne', 'Ola', 'Ærlig', 'Åse'])


class NettleserenSortererNorskTests(SimpleTestCase):
    """`localeCompare` uten språk sorterer etter nettleserens språk — norsk på
    én PC, engelsk på neste. Alle kallene skal si `'nb'`. For ISO-tidsstempler
    endrer det ingenting (prøvd i node 26. sep. 2026), så regelen trenger ingen
    unntak. Ingen kjøretid å prøve: det er en regel om hva kallet sier."""

    def test_hvert_localecompare_sier_nb(self):
        brudd = []
        for fil in sorted((Path(settings.BASE_DIR) / 'static' / 'js').glob('*.js')):
            kilde = fil.read_text(encoding='utf-8')
            start = 0
            while (i := kilde.find('.localeCompare(', start)) >= 0:
                j, dybde = i + len('.localeCompare('), 1
                while dybde:
                    dybde += {'(': 1, ')': -1}.get(kilde[j], 0)
                    j += 1
                if "'nb'" not in kilde[i:j]:
                    brudd.append(f'{fil.name}:{kilde.count(chr(10), 0, i) + 1}')
                start = j
        self.assertEqual(brudd, [], "localeCompare(…, 'nb')")
