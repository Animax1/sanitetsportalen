"""Er det et menneske i den fana? (16. sep. 2026)

**André:** «I /server-status/ ser du hvem som er pålogget, men de trenger ikke
være faktisk aktive og bruke nettsiden — det kan være en fane. Den vil jeg
gjerne kunne se. Og jeg må fortsatt se alle som er innlogget.»

Grunnen til at `expire_date` ikke duger lot seg måle: `SESSION_SAVE_EVERY_REQUEST`
fornyer sesjonen ved **hver** forespørsel, og portalen poller seg selv hvert
5.–30. sekund (lydvarselet 5 s, offline-køen 15 s, tavla og auto-refresh 30 s).
En glemt fane holder derfor sesjonen fersk i åtte timer uten at noen er der.

Derfor bærer fana svaret selv: `apiFetch` sender `X-Portal-Inaktiv` med
sekunder siden siste `pointerdown`/`keydown`/`wheel`/`touchstart`.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from core.admin_status import _list_active_sessions
from core.sesjoner import inaktiv_sekunder as _inaktiv_sekunder
from core.middleware import MAKS_INAKTIV_S, SISTE_INTERAKSJON, les_inaktiv


class LesInaktivTests(SimpleTestCase):
    """Tre beslutninger som hver for seg er en mulig feil."""

    class _Req:
        def __init__(self, verdi=None):
            self.META = {} if verdi is None else {'HTTP_X_PORTAL_INAKTIV': verdi}

    def test_manglende_header_er_en_handling(self):
        """**Null, ikke «ukjent».** Sidelastinger, skjemainnsendinger og alt
        som ikke går gjennom `apiFetch` har ingen header — og det er nettopp
        det et menneske gjør. Pollingen *har* headeren, og det er den som skal
        kunne se gammel ut."""
        self.assertEqual(les_inaktiv(self._Req()), 0)

    def test_soppel_teller_som_en_handling(self):
        """En klient som sender tull skal ikke kunne skjule seg bak det."""
        for verdi in ('', 'x', '1.5', 'NaN', None):
            with self.subTest(verdi=verdi):
                self.assertEqual(les_inaktiv(self._Req(verdi)), 0)

    def test_negativt_og_absurd_klippes(self):
        """Uten klippingen kan en fane skrive seg selv inn i framtida, eller
        oppgi en inaktivitet som er lengre enn sesjonen kan vare."""
        self.assertEqual(les_inaktiv(self._Req('-500')), 0)
        self.assertEqual(les_inaktiv(self._Req(str(MAKS_INAKTIV_S * 10))), MAKS_INAKTIV_S)

    def test_vanlig_verdi_gaar_gjennom(self):
        self.assertEqual(les_inaktiv(self._Req('1800')), 1800)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AktivitetNoteresTests(TestCase):

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='kari', password='x', must_change_password=False)
        self.c = Client()
        self.c.force_login(self.bruker)

    def _sesjon(self):
        return self.c.session.get(SISTE_INTERAKSJON)

    def test_en_vanlig_forespoersel_noterer_naa(self):
        self.c.get('/healthz/')
        self.c.get('/min-profil/')
        self.assertIsNotNone(self._sesjon(), 'en innlogget forespørsel skal notere noe')

    def test_en_poll_med_gammel_interaksjon_noterer_gammelt(self):
        """**Selve poenget.** Fana poller, men ingen har rørt den på en time —
        og da skal sesjonen si det, ikke se fersk ut."""
        naa = timezone.now()
        self.c.get('/min-profil/', HTTP_X_PORTAL_INAKTIV='3600')
        sist = self._sesjon()
        self.assertIsNotNone(sist)
        from datetime import datetime
        alder = (naa - datetime.fromisoformat(sist)).total_seconds()
        self.assertGreater(alder, 3500, 'tidspunktet skal ligge en time tilbake')

    def test_anonyme_forespoersler_noterer_ingenting(self):
        c = Client()
        c.get('/healthz/')
        self.assertIsNone(c.session.get(SISTE_INTERAKSJON))


class InaktivSekunderTests(SimpleTestCase):

    def test_uten_verdi_er_svaret_ukjent_ikke_null(self):
        """**`None`, ikke 0.** En sesjon fra før middlewaren fantes har ingen
        verdi, og «vet ikke» må kunne skilles fra «aktiv nå» — ellers ville
        hver gammel sesjon sett ut som om noen satt der."""
        naa = timezone.now()
        for data in ({}, {SISTE_INTERAKSJON: ''}, {SISTE_INTERAKSJON: 'tull'}):
            with self.subTest(data=data):
                self.assertIsNone(_inaktiv_sekunder(data, naa))

    def test_naiv_tid_avvises(self):
        """En tekst uten tidssone kan ikke trekkes fra et tidssonebevisst
        `now()` — det ville kastet, og et dashbord skal ikke gi 500."""
        self.assertIsNone(
            _inaktiv_sekunder({SISTE_INTERAKSJON: '2026-09-16T12:00:00'}, timezone.now()))

    def test_alderen_regnes_ut(self):
        naa = timezone.now()
        data = {SISTE_INTERAKSJON: (naa - timedelta(minutes=42)).isoformat()}
        self.assertAlmostEqual(_inaktiv_sekunder(data, naa), 42 * 60, delta=2)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ListaViserAlleTests(TestCase):
    """**Aktiviteten er en kolonne, ikke et filter** (André: «jeg må fortsatt
    se alle som er innlogget»). En fane som har stått i to timer er nettopp
    den man leter etter; et filter ville skjult den."""

    def test_en_inaktiv_sesjon_staar_fortsatt_i_lista(self):
        bruker = CustomUser.objects.create_user(
            username='ola', password='x', must_change_password=False)
        c = Client()
        c.force_login(bruker)
        c.get('/min-profil/', HTTP_X_PORTAL_INAKTIV='7200')

        rader = _list_active_sessions()
        mine = [r for r in rader if r['username'] == 'ola']
        self.assertEqual(len(mine), 1, 'sesjonen skal være med')
        self.assertGreater(mine[0]['inaktiv_s'], 7000, 'og vise at ingen er der')


class KlientensMalingTests(SimpleTestCase):
    """`sekunderSidenInteraksjon()` i `portal-utils.js`.

    Regelen ligger som en egen funksjon og ikke som en linje inne i
    `apiFetch`, nettopp for at den skal kunne kjøres uten nettverk.
    """

    def setUp(self):
        from patients.js_test_utils import (PORTAL_UTILS_JS, build_harness,
                                            node_available)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('sekunderSidenInteraksjon', 'merkInteraksjon')),
        ))

    def _kjor(self, snutt):
        from patients.js_test_utils import run_node
        return run_node(self.harness, 'globalThis.sisteInteraksjon = 0;\n' + snutt)

    def test_sekunder_regnes_fra_siste_interaksjon(self):
        ut = self._kjor("""
            globalThis.sisteInteraksjon = 1_000_000;
            console.log(JSON.stringify([
              sekunderSidenInteraksjon(1_000_000),
              sekunderSidenInteraksjon(1_030_000),
              sekunderSidenInteraksjon(1_000_000 + 3600_000),
            ]));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), [0, 30, 3600])

    def test_et_trykk_nullstiller(self):
        """Uten dette ville tallet bare vokse, og en fane man faktisk bruker
        sett like død ut som en glemt."""
        ut = self._kjor("""
            globalThis.sisteInteraksjon = 1_000_000;
            const foer = sekunderSidenInteraksjon(1_060_000);
            globalThis.Date = { now: () => 1_060_000 };
            merkInteraksjon();
            console.log(JSON.stringify([foer, sekunderSidenInteraksjon(1_060_000)]));
        """)
        foer, etter = json.loads(ut.strip().splitlines()[0])
        self.assertEqual((foer, etter), (60, 0))

    def test_klokka_bakover_gir_null_ikke_negativt(self):
        """En klokke som stilles tilbake på en delt drifts-PC skal ikke kunne
        sende et negativt tall — serveren klipper også, men to sperrer er
        billigere enn å finne ut hvilken som sviktet."""
        ut = self._kjor("""
            globalThis.sisteInteraksjon = 2_000_000;
            console.log(String(sekunderSidenInteraksjon(1_000_000)));
        """)
        self.assertEqual(ut.strip().splitlines()[0], '0')


# ── Pollingen som gikk utenom `apiFetch` (26. sep. 2026, A8) ─────────────────
#
# Premisset over — «pollingen *har* headeren» — holdt ikke. Bjella
# (`notifications.js`, alle portalsider, hvert 30. s), pasientsidens
# auto-refresh og server-status brukte rå `fetch`, og manglende header er en
# handling. En glemt, synlig fane sto derfor som «aktiv nå» hvert 30. sekund.
#
# **`ukjent` er det tredje svaret.** Bjella lastes også på admin-sidene, der
# `portal-utils.js` — og dermed målingen — ikke finnes. Der vet fana ikke, og
# sier det: serveren skriver ingenting, verken «aktiv» eller «inaktiv».


class UkjentSkriverIngentingTests(TestCase):

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='ukjent_a8', password='x', must_change_password=False)
        self.c = Client()
        self.c.force_login(self.bruker)

    def test_les_inaktiv_gir_none_for_ukjent(self):
        self.assertIsNone(les_inaktiv(LesInaktivTests._Req('ukjent')))

    @override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
    def test_en_poll_som_ikke_vet_rorer_ikke_tidspunktet(self):
        self.c.get('/min-profil/', HTTP_X_PORTAL_INAKTIV='3600')
        foer = self.c.session.get(SISTE_INTERAKSJON)
        self.c.get('/api/varsler/ulest-antall/', HTTP_X_PORTAL_INAKTIV='ukjent')
        self.assertEqual(self.c.session.get(SISTE_INTERAKSJON), foer)


class BjellaSenderHodetTests(SimpleTestCase):
    """Hele `notifications.js` kjøres i node med stubbet DOM og `fetch`.

    Fila er én IIFE uten navngitte toppnivåfunksjoner, så `build_harness`
    kan ikke hente én funksjon ut av den — derfor hele fila, og pollingen
    fanges der den meldes inn i `setInterval`.
    """

    STUBBER = '''
    const kall = [];
    globalThis.fetch = async (url, opts) => {
      kall.push({ url, hode: (opts && opts.headers) || {} });
      return { ok: true, json: async () => ({ unread: 0 }) };
    };
    const el = () => ({ style: {}, textContent: '', addEventListener() {},
                        querySelectorAll() { return []; } });
    globalThis.document = { getElementById: () => el(), visibilityState: 'visible',
                            addEventListener() {}, querySelector() { return null; } };
    globalThis.window = { location: { pathname: '/ko/' } };
    globalThis.setInterval = (fn) => { globalThis.__poll = fn; };
    '''

    def setUp(self):
        from patients.js_test_utils import JS_DIR, node_available
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.kilde = (JS_DIR / 'notifications.js').read_text(encoding='utf-8')

    def _hodet(self, forspill=''):
        from patients.js_test_utils import run_node
        ut = run_node(self.kilde, '''
            await globalThis.__poll();
            console.log(JSON.stringify(kall.map((k) => k.hode['X-Portal-Inaktiv'] ?? null)));
        ''', preamble=self.STUBBER + forspill)
        return json.loads(ut.strip().splitlines()[0])

    def test_med_maalingen_sender_den_sekundene(self):
        self.assertEqual(self._hodet('globalThis.sekunderSidenInteraksjon = () => 42;'), ['42'])

    def test_uten_maalingen_sier_den_ukjent(self):
        self.assertEqual(self._hodet(), ['ukjent'])


class IngenRaaFetchTests(SimpleTestCase):
    """**En forespørsel utenom `apiFetch` teller som et menneske.** Pasientsiden
    hadde fem slike, og alle ble polling. Unntakene er de som ikke kan bruke
    den, og hver har sin grunn."""

    UNNTAK = {
        'portal-utils.js': 'eier `apiFetch`',
        'notifications.js': 'lastes også der `portal-utils.js` ikke finnes; prøvd over',
        'vaktliste-sw.js': 'service workeren videresender sidens egne forespørsler, med hodene',
    }

    def test_ingen_raa_fetch(self):
        import re

        from patients.js_test_utils import JS_DIR
        funn = []
        for sti in sorted(JS_DIR.glob('*.js')):
            if sti.name in self.UNNTAK:
                continue
            kilde = re.sub(r'/\*.*?\*/', '', sti.read_text(encoding='utf-8'), flags=re.S)
            for nr, linje in enumerate(kilde.splitlines(), 1):
                if linje.lstrip().startswith('//'):
                    continue
                if re.search(r'(?<![\w.])fetch\(', linje):
                    funn.append(f'{sti.name}:{nr}: {linje.strip()}')
        self.assertEqual(funn, [], 'Bruk apiFetch() — den sender X-Portal-Inaktiv')
