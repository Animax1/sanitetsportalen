# -*- coding: utf-8 -*-
"""Fase 6 — koblingen til `/oppdrag` (§6).

`Ressurs.enhet` peker på en `oppdrag.Enhet`. Er den satt, *er* ressursen den
bilen, og sentralbordet kan vise besetningen.

**Avhengighetsretningen går én vei: `vaktliste` → `oppdrag`.** Oppdragsmodulen
importerer ikke vaktlista; sentralbordet henter dette endepunktet og rendrer
svaret. Koblingen ligger i nettleseren, ikke i Python — samme grep som lot
statistikkappen slutte å importere pasientmodulen.

Tre ting bæres av testene her:

1. **Gaten er `les` i vaktliste, ikke i oppdrag.** Komposisjonsregelen fra
   rollemodellen §5: en modul viser bare kilder brukeren har tilgang til.
2. **Svaret er innskrenket med vilje.** Navn, rolle og innsjekkstatus — ikke
   telefonnummer, ikke kompetanser, ikke `notat`. Sentralbordet skal se om
   bilen er klar, ikke lese personalmapper.
3. **Ukoblet er ikke ubemannet.** De to er ulike svar på ulike problemer.
"""
import ast
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from oppdrag.models import Enhet
from patients.models import AppSetting

from . import choices, services
from .models import Mannskap, Vaktpost
from .test_helpers import gruppe, lag_ressurs, lag_rolle, AMBULANSE
from .tests_tilgang import TilgangsBasis, _bruker, _klient


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BesetningTests(TilgangsBasis):

    def setUp(self):
        super().setUp()
        # Vaktlista må høre til portalens aktive vakt: sentralbordet står i
        # den vakta, og besetningen er den som er på bilen *nå*.
        AppSetting.set('aktiv_vakt_id', self.vl.vakt.pk)
        self.enhet = Enhet.objects.create(navn='HGSD 56')
        self.bil = lag_ressurs(vaktliste=self.vl, navn='Ambulanse 1',
                               gruppe=gruppe(AMBULANSE), enhet=self.enhet)
        self.rolle = lag_rolle('Sjåfør', AMBULANSE)
        self.na = timezone.now()

    def _skift(self, person, *, fra=-1, til=7, **felt):
        return Vaktpost.objects.create(
            ressurs=self.bil, mannskap=person, rolle=self.rolle,
            fra_tid=self.na + timedelta(hours=fra),
            til_tid=self.na + timedelta(hours=til), **felt)

    def _hent(self, klient=None, enhet=None):
        return (klient or self.c_vl).get(
            f'/vaktliste/api/enhet/{(enhet or self.enhet).pk}/besetning/')

    # ── Innholdet ────────────────────────────────────────────────────────
    def test_besetningen_er_de_som_har_skift_naa(self):
        self._skift(self.p_hgsd)
        d = self._hent().json()['data']
        self.assertEqual('Ambulanse 1', d['ressurs_navn'])
        self.assertEqual(1, d['antall'])
        self.assertEqual('Kari', d['mannskap'][0]['navn'])
        self.assertEqual('Sjåfør', d['mannskap'][0]['rolle'])

    def test_skift_som_ikke_dekker_naa_er_ikke_med(self):
        """113 spør «er bilen bemannet», ikke «hvem har vakt i helga». En
        liste med tretti rader over to døgn svarer ikke på noe."""
        self._skift(self.p_hgsd, fra=-10, til=-2)     # ferdig
        self._skift(self.p_karmoy, fra=5, til=13)     # ikke begynt
        self.assertEqual(0, self._hent().json()['data']['antall'])

    def test_ledige_plasser_er_ikke_besetning(self):
        Vaktpost.objects.create(
            ressurs=self.bil, mannskap=None,
            fra_tid=self.na - timedelta(hours=1),
            til_tid=self.na + timedelta(hours=7))
        self.assertEqual(0, self._hent().json()['data']['antall'])

    def test_tilstede_utledes_av_stemplene(self):
        vp = self._skift(self.p_hgsd)
        d = self._hent().json()['data']
        self.assertEqual(0, d['tilstede'], 'ingen har stemplet ennå')
        self.assertFalse(d['mannskap'][0]['tilstede'])

        vp.mott_at = self.na
        vp.save()
        d = self._hent().json()['data']
        self.assertEqual(1, d['tilstede'])
        self.assertTrue(d['mannskap'][0]['tilstede'])

    def test_avgatt_er_ikke_tilstede_men_har_moett(self):
        """Tre tilstander, ikke to. «Møtt» og «av vakt» er begge stemplet,
        men bare den ene er i bilen."""
        self._skift(self.p_hgsd, mott_at=self.na - timedelta(hours=1),
                    av_vakt_at=self.na)
        m = self._hent().json()['data']['mannskap'][0]
        self.assertFalse(m['tilstede'])
        self.assertTrue(m['mott'])

    def test_driftflagget_forklarer_null(self):
        """Er ikke innsjekken åpnet, er «0 møtt» ikke et problem — det er en
        port som ikke er åpnet ennå, og panelet må kunne si forskjellen."""
        self._skift(self.p_hgsd)
        self.assertFalse(self._hent().json()['data']['i_drift'])
        self.vl.status = choices.DRIFT
        self.vl.save()
        self.assertTrue(self._hent().json()['data']['i_drift'])

    def test_svaret_baerer_ikke_personalmappa(self):
        """§6, ordrett: ikke telefonnummer, ikke kompetanseliste, ikke notat.
        Sentralbordet skal se om bilen er klar."""
        self.p_hgsd.telefon = '90000000'
        self.p_hgsd.notat = 'Skal hentes 0800'
        self.p_hgsd.save()
        self.p_hgsd.kompetanser.add(self.komp)
        self._skift(self.p_hgsd)

        raa = self._hent().content.decode()
        self.assertNotIn('90000000', raa)
        self.assertNotIn('Skal hentes', raa)
        self.assertNotIn('Sykepleier', raa)
        for felt in ('telefon', 'notat', 'kompetanser', 'brukernavn'):
            self.assertNotIn(felt, raa, f'«{felt}» lekket ut i svaret')

    def test_de_som_er_i_bilen_staar_forst(self):
        """Operatørens spørsmål er «hvem har jeg». De som mangler er den
        andre halvdelen av samme liste, ikke det første man leser."""
        self._skift(Mannskap.objects.create(navn='Åse', korps=self.hgsd))
        self._skift(self.p_hgsd, mott_at=self.na)      # Kari, tilstede
        self._skift(Mannskap.objects.create(navn='Bo', korps=self.hgsd))
        navn = [m['navn'] for m in self._hent().json()['data']['mannskap']]
        self.assertEqual('Kari', navn[0])
        self.assertEqual(['Bo', 'Åse'], navn[1:], 'resten alfabetisk')

    def test_rekkefolgen_hviler_ikke_paa_databasen(self):
        """`rolle` er nullbar, og SQLite (dev) og PostgreSQL (prod) plasserer
        NULL i hver sin ende. En liste som står ulikt lokalt og i drift er en
        feil man aldri ser før den betyr noe — derfor sorteres den i Python,
        på felter som alltid har en verdi.
        """
        import inspect
        kilde = inspect.getsource(services.besetning)
        self.assertNotIn("order_by('rolle__navn'", kilde)
        self.assertIn('mannskap.sort(', kilde)

    # ── Ukoblet mot ubemannet ────────────────────────────────────────────
    def test_ukoblet_enhet_gir_404(self):
        """Noe annet enn «ingen på vakt»: ubemannet er et problem her og nå,
        ukoblet er et oppsett som mangler."""
        annen = Enhet.objects.create(navn='Uten ressurs')
        self.assertEqual(404, self._hent(enhet=annen).status_code)

    def test_bemannet_men_tom_er_200_med_null(self):
        d = self._hent().json()['data']
        self.assertEqual(0, d['antall'])
        self.assertEqual('Ambulanse 1', d['ressurs_navn'])

    def test_ressurs_i_en_annen_vakt_teller_ikke(self):
        """Sentralbordet står i den aktive vakta. Den samme bilen kan være
        koblet i oktobervakta også, og *dens* besetning er ikke hvem som
        sitter i bilen i kveld.

        **Navnene må være ulike for at testen skal måle noe.** Første utgave
        kalte begge «Ambulanse 1», og gikk da grønt uansett hvilken av dem
        endepunktet fant — funnet ved mutasjonstesting.
        """
        annen = services.opprett_planlagt_vakt('Neste vakt')
        # **`rekkefolge=0` med vilje.** `Ressurs.Meta.ordering` sorterer på
        # den, så uten vaktfilteret ville *denne* raden blitt funnet først —
        # og det er nettopp det testen skal fange. Med samme rekkefølge som
        # den aktive vant den aktive uansett, og testen målte ingenting.
        annen_bil = lag_ressurs(vaktliste=annen, navn='Oktoberbilen',
                                gruppe=gruppe(AMBULANSE), enhet=self.enhet,
                                rekkefolge=0)
        Vaktpost.objects.create(
            ressurs=annen_bil, mannskap=self.p_karmoy,
            fra_tid=self.na - timedelta(hours=1),
            til_tid=self.na + timedelta(hours=7))
        self._skift(self.p_hgsd)

        d = self._hent().json()['data']
        self.assertEqual('Ambulanse 1', d['ressurs_navn'],
                         'fant ressursen i feil vakt')
        self.assertEqual(['Kari'], [m['navn'] for m in d['mannskap']])

    # ── Gaten ────────────────────────────────────────────────────────────
    def test_alle_med_les_i_vaktliste_ser_besetningen(self):
        self._skift(self.p_hgsd)
        for navn, c in (('les', self.c_leser), ('korpsfører', self.c_kb),
                        ('skriv_full', self.c_vl), ('admin', self.c_adm)):
            with self.subTest(konto=navn):
                self.assertEqual(200, self._hent(c).status_code)

    def test_uten_vaktlistetilgang_er_det_stengt(self):
        """Komposisjonsregelen (rollemodellen §5): en operatør med
        oppdragstilgang men uten vaktlistetilgang skal ikke få avledet innsyn
        i hvem som går vakt."""
        from accounts.models import ModulTilgang
        bruker = _bruker('operator')
        ModulTilgang.objects.create(bruker=bruker, modul_slug='oppdrag',
                                    nivaa='skriv_full')
        self.assertEqual(403, self._hent(_klient(bruker)).status_code)


class OppdragImportererIkkeVaktlista(SimpleTestCase):
    """Avhengighetsretningen, lest ut av kilden.

    §6: «Oppdragsmodulen skal ikke importere vaktlista.» Koblingen ligger i
    nettleseren — sentralbordet henter `/vaktliste/api/enhet/<pk>/besetning/`
    og rendrer svaret.

    Importene leses med AST og ikke som tekst, slik at omtale i docstrings og
    kommentarer — som det er en del av i akkurat de filene — ikke gir falske
    treff. Samme grep som `StatistikkappenNavngirIngenKilde`.
    """

    def test_ingen_python_import_av_vaktlista(self):
        funn = []
        for sti in sorted(Path(settings.BASE_DIR, 'oppdrag').rglob('*.py')):
            if 'migrations' in sti.parts or sti.name.startswith('tests'):
                continue
            tre = ast.parse(sti.read_text(encoding='utf-8'), filename=str(sti))
            for node in ast.walk(tre):
                navn = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    navn = [node.module]
                elif isinstance(node, ast.Import):
                    navn = [a.name for a in node.names]
                for modul in navn:
                    if modul.split('.')[0] == 'vaktliste':
                        funn.append(f'{sti.name}: {modul}')
        self.assertEqual(funn, [], (
            'Oppdragsmodulen importerer vaktlista — retningen skal gå én '
            'vei, og koblingen ligger i nettleseren:\n  ' + '\n  '.join(funn)))

    def test_sentralbordet_henter_endepunktet_selv(self):
        """Speilet av testen over: retningen holdes ikke bare ved at noe
        *mangler*, men ved at koblingen finnes der den skal."""
        js = Path(settings.BASE_DIR, 'static', 'js',
                  'oppdrag-sentral.js').read_text(encoding='utf-8')
        self.assertIn('/vaktliste/api/enhet/', js)
