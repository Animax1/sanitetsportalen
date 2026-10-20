"""«Krever håndtering» og «Håndtert» på manuelle logglinjer (20. okt. 2026).

André: «Av og til skriver jo våre representant i LSKO et logginnlegg med noe som er til info
for oss, som kanskje ikke haster og heller ikke er en hendelse … er det nyttig at vi kan markere
disse som "håndtert"?» — og så: «en symbol, merke eller en utheving som gjør at dette her, her
må ha en kvittering». «Alle manuelle, men det betyr ikke at absolutt alle linjer som ligger
manuelt trengs å kvitteres og håndteres.»

Tyngden ligger i tjenestelaget: en feil der legger seg i data. Arven ved retting er prøvd for
seg — den er den som ville lukket en oppgave uten at noen hadde gjort den.
"""
from __future__ import annotations

import json

from django.test import Client, SimpleTestCase, override_settings

from ko import services
from ko.models import Logglinje
from patients.js_test_utils import KO_JS, PORTAL_UTILS_JS, build_harness, run_node

from .tests_hendelseslogg import _Grunnlag, _bruker, _gi


class HaandteringenTests(_Grunnlag):

    def _linje(self, tekst='Ring LSKO om vann til scenen', **kw):
        return services.skriv_linje(self.vakt, tekst, bruker=self.operator, **kw)

    def test_merket_ved_skriving_med_hvem(self):
        linje = self._linje(krever_haandtering=True)
        linje.refresh_from_db()
        self.assertTrue(linje.krever_haandtering)
        self.assertEqual(linje.haandtering_krevd_av_navn, 'ko1')
        self.assertFalse(self._linje('Bare til info').krever_haandtering,
                         'ingenting krever det: standarden er en vanlig linje')

    def test_merk_og_ta_av_i_etterkant_og_foerste_merking_staar(self):
        linje = self._linje()
        services.krev_haandtering(linje, bruker=self.andre)
        tid = linje.haandtering_krevd_at
        services.krev_haandtering(linje, bruker=self.operator)
        linje.refresh_from_db()
        self.assertEqual((linje.haandtering_krevd_at, linje.haandtering_krevd_av_navn), (tid, 'ko2'))
        services.fjern_krav(linje, bruker=self.operator)
        linje.refresh_from_db()
        self.assertEqual((linje.haandtering_krevd_at, linje.haandtering_krevd_av_navn), (None, ''))

    def test_haandtert_med_hvem_og_foerste_kvittering_staar(self):
        linje = self._linje(krever_haandtering=True)
        services.haandter(linje, bruker=self.andre)
        tid = linje.haandtert_at
        services.haandter(linje, bruker=self.operator)
        linje.refresh_from_db()
        self.assertEqual((linje.haandtert_at, linje.haandtert_av_navn), (tid, 'ko2'))
        self.assertTrue(linje.krever_haandtering, 'merket står — det er kvitteringen som lukker')

    def test_umerket_linje_kan_ogsaa_kvitteres(self):
        """«Alle manuelle»: en beskjed blir ikke alltid merket først."""
        linje = self._linje()
        services.haandter(linje, bruker=self.andre)
        linje.refresh_from_db()
        self.assertTrue(linje.er_haandtert)

    def test_haandtert_loesner_en_festet_linje(self):
        linje = self._linje(krever_haandtering=True)
        services.fest_linje(linje, bruker=self.operator)
        services.haandter(linje, bruker=self.andre)
        linje.refresh_from_db()
        self.assertFalse(linje.er_festet)
        self.assertEqual((linje.festet_av_id, linje.festet_av_navn), (None, ''))

    def test_angre_aapner_igjen_men_fester_ikke(self):
        linje = self._linje(krever_haandtering=True)
        services.fest_linje(linje, bruker=self.operator)
        services.haandter(linje, bruker=self.andre)
        services.angre_haandtert(linje, bruker=self.andre)
        linje.refresh_from_db()
        self.assertEqual((linje.haandtert_at, linje.haandtert_av_navn), (None, ''))
        self.assertTrue(linje.krever_haandtering, 'den venter igjen')
        self.assertFalse(linje.er_festet, 'festingen var et eget valg')

    def test_systemlinje_fjernet_og_rettet_avvises(self):
        self._hendelse()
        system = self._siste_system()
        fjernet = self._linje('borte')
        services.fjern(fjernet, bruker=self.operator)
        gammel = self._linje('skrivefeil')
        services.korriger(gammel, bruker=self.operator, tekst='rettet')
        for linje in (system, fjernet, gammel):
            linje.refresh_from_db()   # som viewet, som henter linja fersk
            for fn in (services.krev_haandtering, services.haandter):
                with self.subTest(linje=linje.pk, fn=fn.__name__), self.assertRaises(services.Ugyldig):
                    fn(linje, bruker=self.operator)
        self.assertFalse(Logglinje.objects.filter(haandtering_krevd_at__isnull=False).exists())
        self.assertFalse(Logglinje.objects.filter(haandtert_at__isnull=False).exists())

    def test_retting_arver_merket_kvitteringen_og_festingen(self):
        """Klienten finner tilstanden på den gjeldende linjas id. Uten arv lukket en retting
        oppgaven stille — og en festet linje ble løsnet av en retting (rettet samme dag)."""
        aapen = self._linje('Vann til scenen', krever_haandtering=True)
        services.fest_linje(aapen, bruker=self.andre)
        ny = services.korriger(aapen, bruker=self.operator, tekst='Vann til scene sør')
        self.assertEqual(ny.haandtering_krevd_at, aapen.haandtering_krevd_at)
        self.assertEqual(ny.haandtering_krevd_av_navn, 'ko1')
        self.assertEqual((ny.festet_at, ny.festet_av_navn), (aapen.festet_at, 'ko2'))
        self.assertFalse(ny.er_haandtert)

        lukket = self._linje('Strøm til bod 3', krever_haandtering=True)
        services.haandter(lukket, bruker=self.andre)
        ny = services.korriger(lukket, bruker=self.operator, tekst='Strøm til bod 4')
        self.assertEqual((ny.haandtert_at, ny.haandtert_av_navn), (lukket.haandtert_at, 'ko2'))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EndepunkteneTests(_Grunnlag):
    """Portene: «Føre loggen» i KO, vakta, og kroppen. Og at pollen bærer tilstanden."""

    def setUp(self):
        super().setUp()
        _gi(self.operator, 'ko', 'skriv_full')
        self.klient = Client()
        self.klient.force_login(self.operator)
        self.linje = services.skriv_linje(self.vakt, 'Vann til scenen', bruker=self.operator)

    def _post(self, sti, kropp, klient=None, linje=None):
        return (klient or self.klient).post(
            f'/ko/api/logg/{(linje or self.linje).pk}/{sti}/', json.dumps(kropp),
            content_type='application/json')

    def test_skriv_full_merker_og_kvitterer(self):
        r = self._post('krever-haandtering', {'krever': True})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['data']['haandtering_krevd_at'])
        r = self._post('haandtert', {'haandtert': True})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['data']['haandtert_av'], 'ko1')
        self.assertEqual(self._post('haandtert', {'haandtert': False}).json()['data']['haandtert_at'], '')
        self.assertEqual(self._post('krever-haandtering', {'krever': False})
                         .json()['data']['haandtering_krevd_at'], '')

    def test_les_faar_ikke(self):
        leser = _bruker('leser')
        _gi(leser, 'ko', 'les')
        k = Client()
        k.force_login(leser)
        self.assertEqual(self._post('krever-haandtering', {'krever': True}, klient=k).status_code, 403)
        self.assertEqual(self._post('haandtert', {'haandtert': True}, klient=k).status_code, 403)
        self.linje.refresh_from_db()
        self.assertFalse(self.linje.krever_haandtering or self.linje.er_haandtert)

    def test_kroppen_maa_si_ja_eller_nei(self):
        for kropp in ({}, {'krever': 'ja'}, {'krever': 1}):
            with self.subTest(kropp=kropp):
                self.assertEqual(self._post('krever-haandtering', kropp).status_code, 400)
        self.assertEqual(self._post('haandtert', {'haandtert': None}).status_code, 400)

    def test_linje_i_en_annen_vakt_er_404(self):
        from core.models import Vakt
        annen = Vakt.objects.create(navn='i fjor', year=2025, startet=self.linje.tidspunkt)
        gammel = Logglinje.objects.create(vakt=annen, kilde='operator',
                                          tidspunkt=self.linje.tidspunkt, tekst='gammel')
        self.assertEqual(self._post('haandtert', {'haandtert': True}, linje=gammel).status_code, 404)

    def test_skrivingen_tar_imot_merket(self):
        r = self.klient.post('/ko/api/logg/ny/', json.dumps(
            {'tekst': 'Trenger gaffeltruck', 'krever_haandtering': True}), content_type='application/json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()['data']['haandtering_krevd_at'])

    def test_pollen_baerer_tilstanden_hel(self):
        """Merket, kvitteringen og angringen endrer en rad uten ny id — de kommer aldri
        gjennom `?siden=`. Lista sendes hel, med bare linjene der noe er satt."""
        umerket = services.skriv_linje(self.vakt, 'Til info', bruker=self.operator)
        services.krev_haandtering(self.linje, bruker=self.operator)
        siste = Logglinje.objects.order_by('-id').first().pk
        data = self.klient.get(f'/ko/api/logg/?siden={siste}').json()
        self.assertEqual(data['data'], [], 'premisset: ingen nye linjer')
        rader = {r['id']: r for r in data['haandtering']}
        self.assertIn(self.linje.pk, rader)
        self.assertNotIn(umerket.pk, rader)
        services.haandter(self.linje, bruker=self.andre)
        rad = {r['id']: r for r in self.klient.get('/ko/api/logg/').json()['haandtering']}[self.linje.pk]
        self.assertEqual(rad['haandtert_av'], 'ko2')

    def test_pollen_baerer_en_kvittert_linje_som_aldri_var_merket(self):
        """«Håndtert» går på alle manuelle linjer. Mangler en kvittert, umerket linje i lista,
        nullstiller klienten den — og kvitteringen forsvinner fra alle andre skjermer."""
        services.haandter(self.linje, bruker=self.andre)
        rader = {r['id']: r for r in self.klient.get('/ko/api/logg/').json()['haandtering']}
        self.assertEqual(rader[self.linje.pk]['haandtert_av'], 'ko2')
        self.assertEqual(rader[self.linje.pk]['haandtering_krevd_at'], '')

    def test_utskriften_viser_tilstanden(self):
        aapen = services.skriv_linje(self.vakt, 'Vann til scenen B', bruker=self.operator,
                                     krever_haandtering=True)
        services.haandter(self.linje, bruker=self.andre)
        side = self.klient.get('/ko/utskrift/').content.decode()
        self.assertIn('venter på håndtering', side)
        self.assertIn('håndtert av ko2', side)
        self.assertTrue(aapen.krever_haandtering)


# ── Skjermen ─────────────────────────────────────────────────────────────────

LINJE = {
    'id': 1, 'rot': 1, 'kilde': 'operator', 'tidspunkt': '2026-10-20T12:10:00Z',
    'registrert_at': '2026-10-20T12:10:00Z', 'tekst': 'Vann til scenen', 'systemkode': '',
    'forfatter': 'lsko', 'delt_konto': False, 'ansvarsomraade': '', 'korrigerer': None,
    'fjernet': False, 'fjernet_av': '', 'fjernet_at': '', 'festet_at': '', 'festet_av': '',
    'hendelse_id': None, 'hendelse_nummer': None, 'haandtering_krevd_at': '',
    'haandtering_krevd_av': '', 'haandtert_at': '', 'haandtert_av': '',
}
LINJE_FUNKSJONER = ('koKlokke', 'koLinjeMerke', 'koLinjeTekst', 'koLinjeKnapper', 'koLinjeHtml',
                    'koKanSkrive', 'koKanFjerne', 'koVenterPaaHaandtering', 'koHaandteringMerke')


def _linje(**overstyr):
    return json.dumps(LINJE | overstyr)


class LinjaJsTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'nivaaMinst')),
            (KO_JS, LINJE_FUNKSJONER),
            ('static/js/oppdrag-kort.js', ('hendelsesnr',)),
        ))

    def _kjor(self, kode, nivaa='skriv_full'):
        return run_node(self.harness, kode, preamble=f'const window = {{MODUL_TILGANG: {{ko: "{nivaa}"}}}};\n')

    def test_regelen(self):
        ut = self._kjor(f"""
            const v = (o) => koVenterPaaHaandtering(Object.assign({_linje()}, o));
            console.log(JSON.stringify([
              v({{}}), v({{haandtering_krevd_at: 'x'}}),
              v({{haandtering_krevd_at: 'x', haandtert_at: 'y'}}),
              v({{haandtering_krevd_at: 'x', fjernet: true}}),
              v({{haandtering_krevd_at: 'x', kilde: 'system'}}),
            ]));""")
        self.assertEqual(json.loads(ut.splitlines()[0]), [False, True, False, False, False])

    def test_merket_paa_linja_og_escaping(self):
        ut = self._kjor(f"""
            console.log(JSON.stringify([
              koLinjeHtml({_linje()}),
              koLinjeHtml({_linje(haandtering_krevd_at='2026-10-20T12:10:00Z')}),
              koLinjeHtml({_linje(haandtering_krevd_at='x', haandtert_at='2026-10-20T12:32:00Z',
                                  haandtert_av='<img src=x>')}),
            ]));""")
        vanlig, venter, haandtert = json.loads(ut.splitlines()[0])
        self.assertNotIn('ls-krever', vanlig)
        self.assertNotIn('håndtering', vanlig.replace('krever håndtering', '').replace('«krever håndtering»', ''),
                         'en linje til info ser ut som før')
        self.assertIn('ls-krever', venter)
        self.assertIn('Venter på håndtering', venter)
        self.assertIn('Håndtert av &lt;img', haandtert)
        self.assertNotIn('<img', haandtert)
        self.assertNotIn('ls-krever', haandtert)

    def test_knappene_etter_tilstand_og_nivaa(self):
        ut = self._kjor(f"""
            console.log(JSON.stringify([
              koLinjeKnapper({_linje()}),
              koLinjeKnapper({_linje(haandtering_krevd_at='x')}),
              koLinjeKnapper({_linje(haandtert_at='x')}),
            ]));""")
        vanlig, venter, haandtert = json.loads(ut.splitlines()[0])
        self.assertIn('koKrevHaandtering', vanlig)
        self.assertIn('koHaandtert', vanlig, '«Håndtert» på enhver manuell linje')
        self.assertIn('koFjernKrav', venter)
        self.assertIn('koHaandtert', venter)
        self.assertIn('koAngreHaandtert', haandtert)
        self.assertNotIn('koHaandtert"', haandtert)
        leser = self._kjor(f'console.log(koLinjeKnapper({_linje(haandtering_krevd_at="x")}));', nivaa='les')
        self.assertNotIn('Haandt', leser)


class BoksenOeverstJsTests(SimpleTestCase):
    """Gjennom `koTegnLogg()`: det som venter står øverst over «Festet», eldste først, også
    når filteret skjuler linja i strømmen — og forsvinner når det er håndtert."""

    def test_boksen(self):
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'nivaaMinst')),
            (KO_JS, LINJE_FUNKSJONER + ('koTegnLogg', 'koFestetHtml', 'koVenterHtml')),
            ('static/js/oppdrag-kort.js', ('hendelsesnr',)),
        ))
        kode = f"""
            const boks = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: (id) => (id === 'ko-logg-liste' ? boks : null) }};
            globalThis.koIStrommen = () => true;
            globalThis.koLoggfilterTreffer = () => false;   // filteret skjuler alt i strømmen
            globalThis.koLoggfilter = 'x';
            globalThis.koTegnLoggHode = () => {{}};
            globalThis.koLoggTomMelding = () => 'tom';
            globalThis.koLinjer = new Map([
              [1, {_linje(id=1, rot=1, tekst='Eldst', haandtering_krevd_at='2026-10-20T12:00:00Z')}],
              [2, {_linje(id=2, rot=2, tekst='Nyest', haandtering_krevd_at='2026-10-20T12:30:00Z')}],
              [3, {_linje(id=3, rot=3, tekst='Festet beskjed', festet_at='2026-10-20T12:05:00Z')}],
              [4, {_linje(id=4, rot=4, tekst='Ferdig', haandtering_krevd_at='x', haandtert_at='y')}],
            ]);
            koTegnLogg();
            const foer = boks.innerHTML;
            koLinjer.get(1).haandtert_at = '2026-10-20T13:00:00Z';
            koTegnLogg();
            console.log(JSON.stringify([foer, boks.innerHTML]));
        """
        foer, etter = json.loads(run_node(harness, kode, preamble='const window = {MODUL_TILGANG: {ko: "skriv_full"}};\n')
                                 .splitlines()[0])
        venter = foer[:foer.index('Festet</div>')]
        self.assertIn('Venter på håndtering', venter)
        self.assertLess(venter.index('Eldst'), venter.index('Nyest'), 'eldste først')
        self.assertNotIn('Ferdig', venter)
        self.assertIn('data-action="koHaandtert" data-id="1"', venter)
        self.assertIn('Festet beskjed', foer[foer.index('Festet</div>'):])
        self.assertNotIn('Eldst', etter[:etter.index('Festet</div>')], 'håndtert er ute av boksen')


class PollenJsTests(SimpleTestCase):
    """Kallstedet: `koHentLogg()` setter tilstanden fra `haandtering` på alle linjene."""

    def test_pollen(self):
        harness = build_harness(((KO_JS, ('koHentLogg',)),))
        kode = f"""
            globalThis.koLinjer = new Map([[1, {_linje(id=1, rot=1)}],
                                           [2, {_linje(id=2, rot=2, haandtert_at='gammel', haandtert_av='x')}]]);
            globalThis.koSisteId = 2;
            globalThis.koTegnLogg = () => {{}}; globalThis.koTaImotDelte = () => {{}};
            globalThis.koTaImotHendelser = () => {{}}; globalThis.koTaImotPauser = () => {{}};
            globalThis.document = {{ getElementById: () => null }};
            globalThis.apiFetch = async () => ({{ json: async () => ({{ data: [], haandtering: [
              {{ id: 1, haandtering_krevd_at: 'k', haandtering_krevd_av: 'lsko', haandtert_at: '', haandtert_av: '' }}] }}) }});
            await koHentLogg();
            const l = (id) => koLinjer.get(id);
            console.log(JSON.stringify([l(1).haandtering_krevd_at, l(1).haandtering_krevd_av,
                                        l(2).haandtert_at, l(2).haandtert_av]));
        """
        self.assertEqual(json.loads(run_node(harness, kode).splitlines()[0]), ['k', 'lsko', '', ''],
                         'en linje som ikke står i lista, har ingenting satt — angringen når fram')
