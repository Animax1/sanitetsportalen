"""Sentralbordet i `/ko/` (pulje 4) — at det er det samme sentralbordet.

**Kort fil med vilje.** Flata *er* `/oppdrag/` sin: samme kontekst, samme
maler, samme JS, samme endepunkter. Reglene i den er prøvd der, og å prøve dem
om igjen her ville vært to kopier av samme test. Det som prøves her er at det
er samme kilde, og gaten rundt.

Pulje 3 hadde en kort stund `/ko/api/ressurser/` med `ko:les` som gate. Den er
borte: oppdragsdata gates av **oppdragsmodulen**, også når sida er KO (André,
18. sep. 2026).
"""
from __future__ import annotations

from django.test import Client, RequestFactory, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from core.vakt import vakt_for_year
from oppdrag.models import Enhet


def _bruker(navn, **kwargs):
    return CustomUser.objects.create_user(
        username=navn, password='x', must_change_password=False, **kwargs)


def _gi(bruker, modul, nivaa):
    ModulTilgang.objects.update_or_create(
        bruker=bruker, modul_slug=modul, defaults={'nivaa': nivaa})
    return bruker


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KontekstenErDenSammeTests(TestCase):
    """Én kilde, to sider.

    En verdimengde som kom til i `/oppdrag/` og ikke her ville gitt et tomt
    nedtrekk på KO-sida — en feil som ser ut som en datafeil og ikke som en
    glemt linje.
    """

    def setUp(self):
        vakt_for_year(2026)
        self.bruker = _gi(_bruker('operator'), 'oppdrag', 'skriv_leder')
        _gi(self.bruker, 'ko', 'skriv_full')

    def test_ko_faar_hele_sentralbordkonteksten(self):
        from oppdrag.views import sentralbordkontekst

        rf = RequestFactory()
        req = rf.get('/ko/')
        req.user = self.bruker
        fasit = sentralbordkontekst(req)

        self.client.force_login(self.bruker)
        ko = self.client.get('/ko/').context
        for noekkel in fasit:
            with self.subTest(noekkel=noekkel):
                self.assertIn(noekkel, ko)
                self.assertEqual(ko[noekkel], fasit[noekkel])

    def test_begge_sidene_laster_de_samme_skriptene(self):
        """Samme filer i samme rekkefølge. Ingen bundler, så rekkefølgen *er*
        kontrakten — og to sider som lastet ulikt ville hatt to ulike
        feilmoduser for samme kode."""
        self.client.force_login(self.bruker)

        def skript(sti):
            ut = []
            for linje in self.client.get(sti).content.decode().splitlines():
                if '<script src=' in linje and '/static/js/' in linje:
                    ut.append(linje.split('/static/js/')[1].split('.')[0])
            return ut

        fra_oppdrag = skript('/oppdrag/')
        fra_ko = skript('/ko/')
        felles = [f for f in fra_oppdrag if f.startswith('oppdrag')]
        self.assertEqual([f for f in fra_ko if f.startswith('oppdrag')], felles,
                         'KO laster ikke sentralbordfilene likt')
        self.assertIn('ko', fra_ko)
        self.assertNotIn('ko', fra_oppdrag)

    def test_alle_sentralbordfilene_lastes(self):
        """**Sperrehake mot testen over.** Den krever at de to sidene er
        *like*, ikke at de er *komplette* — begge leser samme malbit, så en
        fil som faller ut, faller ut begge steder og likheten består.
        Mutanten overlevde nøyaktig sånn (18. sep. 2026).

        Fasiten er `OPPDRAG_SENTRAL_JS`, som `core/tests_js_splitt.py` holder i
        takt med filene på disk. Rekkefølgen er lasterekkefølgen: uten bundler
        *er* den kontrakten.
        """
        from patients.js_test_utils import OPPDRAG_SENTRAL_JS

        ventet = [f.stem for f in OPPDRAG_SENTRAL_JS]
        self.client.force_login(self.bruker)
        for sti in ('/oppdrag/', '/ko/'):
            with self.subTest(sti=sti):
                lastet = [l.split('/static/js/')[1].split('.')[0]
                          for l in self.client.get(sti).content.decode().splitlines()
                          if '<script src=' in l and '/static/js/' in l]
                self.assertEqual([f for f in lastet if f.startswith('oppdrag')],
                                 ventet,
                                 'en sentralbordfil mangler eller står i feil '
                                 'rekkefølge')

    def test_ko_laster_stilarkene_sentralbordet_er_tegnet_med(self):
        """Kortene og radene er stilt i `oppdrag.css`, ikke i markupen.

        Tre forsøk på å få lista i `/ko/` til å se ut som i `/oppdrag/` gikk
        grønne på server- og JS-siden og feilet i nettleseren (18. sep. 2026):
        samme markup, samme data — men sida lastet aldri arket klassene står
        i, så kortene ble ren tekst. Regelen: hvert stilark `/oppdrag/` laster,
        laster `/ko/` også, og **før** `ko.css`, så konsollen får siste ord.
        """
        self.client.force_login(self.bruker)

        def stilark(sti):
            # Navnet før første punktum: WhiteNoise hasher fila til
            # `oppdrag.bb76….css`, og testen skal ikke bry seg om hashen.
            return [l.split('/static/css/')[1].split('.')[0]
                    for l in self.client.get(sti).content.decode().splitlines()
                    if 'stylesheet' in l and '/static/css/' in l]

        fra_oppdrag = stilark('/oppdrag/')
        fra_ko = stilark('/ko/')
        # Sperrehake: er `oppdrag.css` borte fra /oppdrag/ også, er kravet
        # under tomt — og det er den fila hele regelen handler om.
        self.assertIn('oppdrag', fra_oppdrag)
        for ark in fra_oppdrag:
            with self.subTest(ark=ark):
                self.assertIn(ark, fra_ko, f'/ko/ laster ikke {ark}')
        self.assertLess(fra_ko.index('oppdrag'), fra_ko.index('ko'),
                        'ko.css skal lastes etter oppdrag.css')

    def test_begge_sidene_har_de_samme_flatene(self):
        """ID-ene koden skriver til. En side som manglet én ville hatt en
        knapp som åpnet ingenting."""
        self.client.force_login(self.bruker)
        opp = self.client.get('/oppdrag/').content.decode()
        ko = self.client.get('/ko/').content.decode()
        for ident in ('id="enhetsliste"', 'id="oppdragsliste"',
                      'id="av-vakt-teller"', 'id="nyttOppdragModal"',
                      'id="oppdragDetaljModal"', 'id="historikkModal"'):
            with self.subTest(ident=ident):
                self.assertIn(ident, opp)
                self.assertIn(ident, ko)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class OppdragsflataGatesAvOppdragsmodulenTests(TestCase):
    """**Komposisjonsregelen fra rollemodellen §5** (André, 18. sep. 2026).

    KO *viser* oppdragsmodulens data, og hvem som får se dem er
    oppdragsmodulens sak. Alternativet — egne KO-nivåer foran de samme
    endepunktene — ville lagt tilgangsmodellen to steder.
    """

    def setUp(self):
        vakt_for_year(2026)
        Enhet.objects.create(navn='Haugesund 56', pa_vakt=True)
        self.client = Client()

    def test_valglistene_krever_skriv_leder(self):
        """Verdimengdene settes opp av `skriv_leder` (André, 12. sep. 2026),
        og nivået er oppdragsmodulens — også på KO-sida. Vinduet heter
        «KO-innstillinger» der (18. sep. 2026), og KOs egen fane
        (ressursbehovene) har sin egen dør: KO-leder."""
        bruker = _gi(_bruker('skriver'), 'ko', 'skriv_full')
        _gi(bruker, 'oppdrag', 'skriv_full')
        self.client.force_login(bruker)
        markup = self.client.get('/ko/').content.decode()
        self.assertNotIn('data-bs-target="#valglisterModal"', markup)
        self.assertNotIn('data-verdifane="ressursbehov"', markup)

        _gi(bruker, 'oppdrag', 'skriv_leder')
        markup = self.client.get('/ko/').content.decode()
        self.assertIn('data-bs-target="#valglisterModal"', markup)
        self.assertIn('data-verdifane="lokasjoner"', markup)
        self.assertNotIn('data-verdifane="ressursbehov"', markup,
                         'oppdragsleder er ikke KO-leder')

    def test_ko_leder_faar_ressursbehovfanen_uten_oppdragsleder(self):
        """Den andre døra: KO-leder uten oppdragsleder-nivå ser
        «KO-innstillinger» med bare ressursbehovene."""
        bruker = _gi(_bruker('koleder'), 'ko', 'skriv_leder')
        _gi(bruker, 'oppdrag', 'skriv_full')
        self.client.force_login(bruker)
        markup = self.client.get('/ko/').content.decode()
        self.assertIn('data-bs-target="#valglisterModal"', markup)
        self.assertIn('data-verdifane="ressursbehov"', markup)
        self.assertNotIn('data-verdifane="lokasjoner"', markup)
        self.assertIn('KO-innstillinger', markup)

    def test_uten_oppdragstilgang_tegnes_ikke_flata(self):
        self.client.force_login(_gi(_bruker('bare_ko'), 'ko', 'skriv_leder'))
        markup = self.client.get('/ko/').content.decode()
        self.assertNotIn('id="oppdragsliste"', markup)
        self.assertNotIn('id="nyttOppdragModal"', markup)
        self.assertIn('oppdragsmodulen', markup,
                      'sida skal si hvorfor flata mangler, ikke bare utelate den')
        # Loggen står uansett — den er KOs egen.
        self.assertIn('id="ko-logg-form"', markup)

    def test_med_oppdragstilgang_tegnes_den(self):
        bruker = _gi(_bruker('begge'), 'ko', 'skriv_full')
        _gi(bruker, 'oppdrag', 'les')
        self.client.force_login(bruker)
        markup = self.client.get('/ko/').content.decode()
        self.assertIn('id="oppdragsliste"', markup)
        self.assertIn('id="enhetsliste"', markup)

    def test_knappene_foelger_oppdragsnivaaet_og_ikke_ko(self):
        """`les` i oppdrag ser lista, men skal ikke ha «Nytt oppdrag» — selv
        med `skriv_leder` i KO."""
        bruker = _gi(_bruker('leser'), 'ko', 'skriv_leder')
        _gi(bruker, 'oppdrag', 'les')
        self.client.force_login(bruker)
        markup = self.client.get('/ko/').content.decode()
        # **Både knappen og modalen.** De gates hver for seg, i hver sin
        # malbit, og en test som bare så modalen lot knappen stå igjen — den
        # ville åpnet ingenting. Mutanten overlevde nøyaktig sånn.
        self.assertNotIn('id="nyttOppdragModal"', markup)
        self.assertNotIn('data-bs-target="#nyttOppdragModal"', markup)
        self.assertNotIn('data-bs-target="#enheterModal"', markup)

        _gi(bruker, 'oppdrag', 'skriv_full')
        markup = self.client.get('/ko/').content.decode()
        self.assertIn('id="nyttOppdragModal"', markup)
        self.assertIn('data-bs-target="#nyttOppdragModal"', markup)

    def test_ko_har_ingen_egne_oppdragsendepunkter(self):
        """Ingen proxy foran oppdragsmodulen. `/ko/api/ressurser/` fantes i
        pulje 3 og er borte — den gatet oppdragsdata på `ko:les`."""
        self.client.force_login(_gi(_bruker('skriver'), 'ko', 'skriv_leder'))
        for sti in ('/ko/api/ressurser/', '/ko/api/oppdrag/'):
            with self.subTest(sti=sti):
                self.assertEqual(self.client.get(sti).status_code, 404)
