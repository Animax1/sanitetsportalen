"""Fanen «Lag» (pulje 3): tallene og gaten.

**Tallene** prøves med tidspunkter i UTC, slik ORM-en gir dem i prod — ikke i
norsk tid. Ellers kunne timefordelingen gått over til UTC-timen uten at noe ble
rødt (CLAUDE.md, «fikstureringen bar ikke prod-formen»).

**Gaten** er `statistikk: les` **og** `park: les` (B17): ledelsen ser fanen,
en KO-operatør med statistikk for andre kilder gjør det ikke.
"""
from __future__ import annotations

from datetime import datetime, timezone as dt_tz

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import ModulTilgang
from core.vakt import hent_aktiv_vakt

from . import services
from .models import Problemstilling, Registrering, Utfall
from .statistikk import park_stats
from .tests import _bruker, _Grunnlag


class TalleneTests(_Grunnlag):

    def _reg(self, *, lag=None, ps='Skade bein/fot', utfall='Behandlet på stedet', antall=1,
             utc=None, kilde='ingen', endret=False, sted=None):
        rad, _ = services.registrer(self.lenke, self.vakt, self._data(
            lag=(lag or self.lag1).pk, sted=(sted or self.park).pk,
            problemstilling=Problemstilling.objects.get(navn=ps).pk,
            utfall=Utfall.objects.get(navn=utfall).pk, antall=antall,
            forhandsvalg_kilde=kilde, forhandsvalg_endret=endret))
        if utc is not None:
            Registrering.objects.filter(pk=rad.pk).update(registrert_at=utc)
        return rad

    def test_kontakter_er_summen_av_antall_og_slettede_telles_ikke(self):
        self._reg(antall=3)
        self._reg(antall=2, lag=self.lag2)
        slettet = self._reg(antall=10)
        services.slett_registrering(slettet, bruker=None, grunn='feil')
        s = park_stats(self.vakt)['summary']
        self.assertEqual((s['registreringer'], s['kontakter'], s['lag'], s['slettet']), (2, 5, 2, 1))

    def test_fordelingen_flest_kontakter_foerst(self):
        self._reg(ps='Brannskade', antall=1)
        self._reg(ps='Kramper', antall=4)
        self._reg(ps='Brannskade', antall=1)
        ps = park_stats(self.vakt)['per_problemstilling']
        self.assertEqual([(p['navn'], p['registreringer'], p['kontakter']) for p in ps],
                         [('Kramper', 1, 4), ('Brannskade', 2, 2)])

    def test_timen_er_norsk_tid(self):
        # 20:30 UTC er 22:30 i Norge om sommeren (UTC+2).
        self._reg(antall=2, utc=datetime(2026, 7, 1, 20, 30, tzinfo=dt_tz.utc))
        timer = park_stats(self.vakt)['per_time']
        self.assertEqual(len(timer), 24)
        self.assertEqual([(t['time'], t['kontakter']) for t in timer if t['kontakter']], [(22, 2)],
                         'kontakter, ikke registreringer — og i norsk tid')

    def test_kryss_problemstilling_utfall(self):
        self._reg(ps='Kramper', utfall='Tilkalt bil', antall=2)
        self._reg(ps='Kramper', utfall='Behandlet på stedet')
        k = park_stats(self.vakt)['kryss']
        rad = k['celler'][k['rader'].index('Kramper')]
        self.assertEqual(dict(zip(k['kolonner'], rad)), {'Tilkalt bil': 2, 'Behandlet på stedet': 1})

    def test_maalingen_av_forhaandsvalget(self):
        self._reg(kilde='ko', endret=True)
        self._reg(kilde='ko')
        self._reg(kilde='ko')
        self._reg(kilde='registrering')
        f = {x['kilde']: x for x in park_stats(self.vakt)['forhandsvalg']}
        self.assertEqual((f['ko']['registreringer'], f['ko']['endret'], f['ko']['andel_endret']), (3, 1, 33))
        self.assertEqual(f['registrering']['endret'], 0)
        self.assertNotIn('telefon', f, 'kilder uten registreringer står ikke')

    def test_per_lag_og_sted(self):
        self._reg(antall=2, sted=self.club)
        self._reg(lag=self.lag2)
        d = park_stats(self.vakt)
        self.assertEqual([(l['navn'], l['kontakter']) for l in d['per_lag']],
                         [('Sandnes 2.1', 2), ('Sandnes 2.2', 1)])
        self.assertEqual({s['navn']: s['kontakter'] for s in d['per_sted']}, {'Club': 2, 'Parkscene': 1})

    def test_bare_denne_vakta(self):
        from core.models import Vakt
        self._reg(antall=4)
        annen = Vakt.objects.create(navn='Annen vakt', year=2025, startet=timezone.now())
        self.assertEqual(park_stats(annen)['summary']['kontakter'], 0)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class GatenTests(TestCase):

    def _klient(self, navn, tilganger):
        b = _bruker(navn)
        for slug, nivaa in tilganger:
            ModulTilgang.objects.create(bruker=b, modul_slug=slug, nivaa=nivaa)
        c = Client()
        c.force_login(b)
        return c

    URL = '/statistikk/api/kilde/park/full-stats/'

    def test_ledelsen_ser_fanen(self):
        c = self._klient('leder', [('statistikk', 'les'), ('park', 'les'), ('patients', 'les')])
        self.assertEqual(c.get(self.URL).status_code, 200)
        html = c.get('/statistikk/').content.decode()
        self.assertIn('data-arg="park"', html)
        self.assertIn('>Lag<', html)
        self.assertIn('js/statistikk-park.', html)

    def test_operatoren_uten_park_ser_den_ikke(self):
        hent_aktiv_vakt()
        c = self._klient('op', [('statistikk', 'les'), ('ko', 'les'), ('patients', 'les')])
        self.assertIn(c.get(self.URL).status_code, (403, 404))
        html = c.get('/statistikk/').content.decode()
        self.assertNotIn('id="kilde-park"', html)
        self.assertNotIn('statistikk-park.', html)

    def test_park_uten_statistikk_gir_ingen_statistikk(self):
        c = self._klient('bare', [('park', 'les')])
        self.assertEqual(c.get('/statistikk/').status_code, 403)
        self.assertEqual(c.get(self.URL).status_code, 403)


class EnesteKildeTests(TestCase):
    """Er «Lag» eneste fane, rendres ingen fanerad, og panelet må være aktivt —
    ellers står siden tom (`aktivKilde()` leser det aktive panelet)."""

    def test_panelet_er_aktivt_naar_det_er_alene(self):
        b = _bruker('alene')
        for slug in ('statistikk', 'park'):
            ModulTilgang.objects.create(bruker=b, modul_slug=slug, nivaa='les')
        c = Client()
        c.force_login(b)
        with override_settings(SECURE_SSL_REDIRECT=False):
            html = c.get('/statistikk/').content.decode()
        self.assertIn('class="kilde-panel active" id="kilde-park"', html)
