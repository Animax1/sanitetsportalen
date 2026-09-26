"""Bemanningsfanen (statistikk pulje 7c, 21. sep. 2026): belastning mot bemanning.

Reglene bor i `vaktliste/statistikk.py`; intervallhjelperne prøves alene, og
tallene gjennom `bemanning_stats`. Kilden krever `les_alle` — det prøves her
og ikke i statistikkappen, fordi det er denne handleren som deklarerer det.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.vakt import hent_aktiv_vakt
from oppdrag import choices
from oppdrag import services as oservices
from oppdrag.models import Enhet, Lokasjon, Oppdrag
from vaktliste.models import Korps, Mannskap, Vaktliste, Vaktpost
from vaktliste.intervaller import slaa_sammen
from vaktliste.statistikk import bemanning_stats, lengste_hull
from vaktliste.test_helpers import LAG, gruppe, lag_ressurs


class IntervallTests(TestCase):
    def setUp(self):
        self.t0 = timezone.now().replace(minute=0, second=0, microsecond=0)

    def _t(self, m):
        return self.t0 + timedelta(minutes=m)

    def test_union_slaar_sammen_overlapp_og_kant(self):
        self.assertEqual(
            slaa_sammen([(self._t(0), self._t(60)), (self._t(30), self._t(90)),
                   (self._t(90), self._t(100)), (self._t(200), self._t(210)),
                   (self._t(300), self._t(300))]),
            [(self._t(0), self._t(100)), (self._t(200), self._t(210))])

    def test_lengste_hull(self):
        bemannet = [(self._t(0), self._t(480))]
        opptatt = [(self._t(60), self._t(90)), (self._t(70), self._t(120)), (self._t(400), self._t(420))]
        # Hullene: 0–60, 120–400 (280), 420–480.
        self.assertEqual(lengste_hull(bemannet, opptatt), 280.0)

    def test_lengste_hull_taaler_usortert_og_overlappende(self):
        bemannet = [(self._t(0), self._t(300))]
        opptatt = [(self._t(200), self._t(210)), (self._t(60), self._t(90)), (self._t(70), self._t(120))]
        self.assertEqual(lengste_hull(bemannet, opptatt), 90.0)   # 210 → 300

    def test_lengste_hull_uten_oppdrag_er_hele_bemanningen(self):
        self.assertEqual(lengste_hull([(self._t(0), self._t(120))], []), 120.0)

    def test_oppdrag_utenfor_bemannet_tid_teller_ikke(self):
        bemannet = [(self._t(100), self._t(200))]
        opptatt = [(self._t(0), self._t(50)), (self._t(150), self._t(160)), (self._t(250), self._t(260))]
        # Hullene innenfor: 100–150 og 160–200. Oppdraget etter slutten skal
        # ikke forlenge det siste hullet til 250.
        self.assertEqual(lengste_hull(bemannet, opptatt), 50.0)


class Basis(TestCase):
    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.vl = Vaktliste.objects.create(vakt=self.vakt)
        self.korps = Korps.objects.create(navn='Testkorps')
        self.enhet = Enhet.objects.create(navn='Ambulanse 1', pa_vakt=True)
        self.enhet2 = Enhet.objects.create(navn='Ambulanse 2', pa_vakt=True)
        self.lokasjon = Lokasjon.objects.create(navn='Scene sør')
        self.bil = lag_ressurs(vaktliste=self.vl, navn='Ambulanse 1', enhet=self.enhet)
        self.lag1 = lag_ressurs(vaktliste=self.vl, navn='Lag 1', gruppe=gruppe(LAG))
        self.bruker = CustomUser.objects.create_user(username='op', password='x', must_change_password=False)
        # 20:00 lokal i går; «nå» er 23:00.
        self.t0 = timezone.localtime(timezone.now()).replace(
            hour=20, minute=0, second=0, microsecond=0) - timedelta(days=1)
        self.naa = self.t0 + timedelta(hours=3)
        self._n = 0

    def _t(self, m):
        return self.t0 + timedelta(minutes=m)

    def _post(self, ressurs, fra, til, *, mott=None, avmeldt=False, mannskap=None):
        self._n += 1
        person = mannskap or Mannskap.objects.create(navn=f'Person {self._n}', korps=self.korps)
        return Vaktpost.objects.create(
            ressurs=ressurs, mannskap=person, fra_tid=self._t(fra), til_tid=self._t(til),
            mott_at=self._t(mott) if mott is not None else None,
            avmeldt_at=self._t(fra) if avmeldt else None)

    def _oppdrag(self, enhet, opprettet, ledig=None):
        o = Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=oservices.neste_oppdragsnummer(self.vakt),
            enhet=enhet, lokasjon=self.lokasjon, problemstilling='Fall', hastegrad='Haster')
        Oppdrag.objects.filter(pk=o.pk).update(created_at=self._t(opprettet))
        o.enheter.update(varslet_at=self._t(opprettet))
        if ledig is not None:
            oservices.sett_status(o, choices.LEDIG, bruker=self.bruker, tidspunkt=self._t(ledig), enhet=enhet)
        return o

    def stats(self):
        return bemanning_stats(self.vakt, naa=self.naa)


class PerTimeTests(Basis):
    def test_personer_mott_lag_og_enheter_per_time(self):
        self._post(self.bil, 0, 120, mott=5)          # 20:00–22:00, møtt
        self._post(self.bil, 60, 180)                 # 21:00–23:00, ikke møtt
        self._post(self.lag1, 30, 90, mott=30)        # 20:30–21:30
        self._post(self.lag1, 0, 60, avmeldt=True)    # avmeldt: teller ikke

        per = {r['time']: r for r in self.stats()['per_time']}
        self.assertEqual((per[20]['personer'], per[20]['mott']), (2, 2))
        self.assertEqual((per[21]['personer'], per[21]['mott']), (3, 2))
        self.assertEqual((per[22]['personer'], per[22]['mott']), (1, 0))
        self.assertEqual((per[20]['lag'], per[21]['lag'], per[22]['lag']), (1, 1, 0))
        # To skift på samme bil er én enhet.
        self.assertEqual((per[21]['enheter'], per[23]['enheter']), (1, 0))

    def test_en_person_paa_to_overlappende_skift_er_en(self):
        person = Mannskap.objects.create(navn='Same', korps=self.korps)
        self._post(self.bil, 0, 120, mannskap=person, mott=0)
        self._post(self.lag1, 60, 180, mannskap=person, mott=60)
        per = {r['time']: r for r in self.stats()['per_time']}
        self.assertEqual((per[21]['personer'], per[21]['mott']), (1, 1))

    def test_mott_teller_fra_mott_tidspunktet(self):
        self._post(self.bil, 0, 180, mott=70)       # møtt 21:10
        per = {r['time']: r for r in self.stats()['per_time']}
        self.assertEqual((per[20]['mott'], per[21]['mott']), (0, 1))

    def test_skift_som_slutter_paa_hel_time(self):
        self._post(self.bil, 0, 120)                 # 20:00–22:00
        per = {r['time']: r for r in self.stats()['per_time']}
        self.assertEqual((per[21]['personer'], per[22]['personer']), (1, 0))


class SummaryTests(Basis):
    def test_timer_og_oppdrag_per_enhetstime(self):
        person = Mannskap.objects.create(navn='Same', korps=self.korps)
        self._post(self.bil, 0, 120, mott=0, mannskap=person)    # 2 t
        self._post(self.bil, 60, 180, mannskap=person)           # overlapper: bilen bemannet 3 t
        self._post(self.lag1, 0, 60)                             # lag 1 t
        self._oppdrag(self.enhet, 10, ledig=40)
        self._oppdrag(self.enhet, 50, ledig=70)
        self._oppdrag(self.enhet2, 20, ledig=30)                 # bil uten ressurs

        s = self.stats()['summary']
        self.assertEqual((s['personer'], s['skift'], s['mott']), (2, 3, 1))
        self.assertEqual(s['persontimer'], 5.0)
        self.assertEqual(s['enhetstimer'], 3.0, 'union, ikke sum')
        self.assertEqual(s['lagtimer'], 1.0)
        self.assertEqual(s['antall_oppdrag'], 3)
        self.assertEqual(s['oppdrag_per_enhetstime'], 1.0)

    def test_uten_vaktliste(self):
        self.vl.delete()
        s = self.stats()
        self.assertFalse(s['har_vaktliste'])
        self.assertIsNone(s['summary']['oppdrag_per_enhetstime'])
        self.assertEqual(s['summary']['enhetstimer'], 0)


class UtnyttelseTests(Basis):
    def test_andel_og_lengste_ledig(self):
        self._post(self.bil, 0, 120)                  # bemannet 20:00–22:00
        self._oppdrag(self.enhet, 10, ledig=40)       # 30 min
        self._oppdrag(self.enhet, 30, ledig=70)       # overlapper: til 70 → 60 min opptatt
        u = self.stats()['utnyttelse']['Ambulanse 1']
        self.assertEqual(u['bemannet_timer'], 2.0)
        self.assertEqual(u['oppdrag_timer'], 1.0)
        self.assertEqual(u['andel'], 50)
        self.assertEqual(u['lengste_ledig'], 50.0)   # 70 → 120
        self.assertEqual(u['oppdrag'], 2)

    def test_to_ressurser_paa_samme_bil_telles_en_gang(self):
        """`Ressurs.enhet` er en FK: dagbilen og nattbilen kan være samme
        enhet. Overlapper de, er bilen bemannet i unionen av tida — ikke i
        summen. Ingen test holdt dette før 26. sep. 2026 (E5, mutant)."""
        natt = lag_ressurs(vaktliste=self.vl, navn='Ambulanse 1 natt', enhet=self.enhet)
        self._post(self.bil, 0, 120)                  # 20:00–22:00
        self._post(natt, 60, 180)                     # 21:00–23:00
        self._oppdrag(self.enhet, 0, ledig=30)
        u = self.stats()['utnyttelse']['Ambulanse 1']
        self.assertEqual(u['bemannet_timer'], 3.0, 'union, ikke 4 t')
        self.assertEqual(u['lengste_ledig'], 150.0)  # 20:30 → 23:00

    def test_bil_uten_ressurs_er_ukjent(self):
        self._oppdrag(self.enhet2, 10, ledig=40)
        u = self.stats()['utnyttelse']['Ambulanse 2']
        self.assertEqual((u['bemannet_timer'], u['andel'], u['lengste_ledig']), (None, None, None))
        self.assertEqual(u['oppdrag_timer'], 0.5)

    def test_paagaaende_oppdrag_regnes_til_naa(self):
        self._post(self.bil, 0, 180)
        self._oppdrag(self.enhet, 120)                # ikke ledig → til 23:00
        u = self.stats()['utnyttelse']['Ambulanse 1']
        self.assertEqual(u['oppdrag_timer'], 1.0)
        self.assertEqual(u['andel'], 33)

    def test_andelen_kappes_ved_hundre(self):
        self._post(self.bil, 0, 60)
        self._oppdrag(self.enhet, 0, ledig=120)
        self.assertEqual(self.stats()['utnyttelse']['Ambulanse 1']['andel'], 100)

    def test_median_over_enhetene(self):
        enhet3 = Enhet.objects.create(navn='Ambulanse 3', pa_vakt=True)
        bil2 = lag_ressurs(vaktliste=self.vl, navn='Ambulanse 2', enhet=self.enhet2)
        bil3 = lag_ressurs(vaktliste=self.vl, navn='Ambulanse 3', enhet=enhet3)
        self._post(self.bil, 0, 120); self._post(bil2, 0, 120); self._post(bil3, 0, 120)
        self._oppdrag(self.enhet, 0, ledig=60)        # 50 %
        self._oppdrag(self.enhet2, 0, ledig=120)      # 100 %
        self._oppdrag(enhet3, 0, ledig=120)           # 100 %
        # Median 100, snitt 83 — tre verdier, så de to ikke er like.
        self.assertEqual(self.stats()['summary']['utnyttelse_median'], 100)


class GateTests(TestCase):
    KILDEN = '/statistikk/api/kilde/vaktliste/full-stats/'

    def _med(self, navn, tilganger):
        bruker = CustomUser.objects.create_user(username=navn, password='x', must_change_password=False)
        for modul, nivaa in tilganger:
            ModulTilgang.objects.update_or_create(bruker=bruker, modul_slug=modul, defaults={'nivaa': nivaa})
        c = Client(); c.force_login(bruker); return c

    def test_handleren_krever_les_alle(self):
        from core.stats import get_handler
        self.assertEqual(get_handler('vaktliste').nivaa, 'les_alle')

    def test_les_paa_vaktlista_gir_ingen_fane(self):
        """`les` er «sitt eget korps»; hele bemanningen er ikke det."""
        c = self._med('korpsleser', [('statistikk', 'les'), ('vaktliste', 'les')])
        html = c.get('/statistikk/').content.decode('utf-8') if c.get('/statistikk/').status_code == 200 else ''
        self.assertNotIn('kilde-vaktliste', html)
        self.assertEqual(c.get(self.KILDEN).status_code, 403)

    def test_les_alle_gir_fane_fil_og_tall(self):
        c = self._med('alleleser', [('statistikk', 'les'), ('vaktliste', 'les_alle')])
        html = c.get('/statistikk/').content.decode('utf-8')
        self.assertIn('kilde-vaktliste', html)
        self.assertRegex(html, r'statistikk-bemanning(\.[0-9a-f]{8,})?\.js')
        svar = c.get(self.KILDEN)
        self.assertEqual(svar.status_code, 200)
        self.assertIn('utnyttelse', svar.json())

    def test_svaret_baerer_ingen_personnavn(self):
        import json
        vakt = hent_aktiv_vakt()
        vl = Vaktliste.objects.create(vakt=vakt)
        r = lag_ressurs(vaktliste=vl, navn='Lag 1', gruppe=gruppe(LAG))
        korps = Korps.objects.create(navn='K')
        m = Mannskap.objects.create(navn='Kari Nordmann Hemmelig', korps=korps)
        naa = timezone.now()
        Vaktpost.objects.create(ressurs=r, mannskap=m, fra_tid=naa - timedelta(hours=1), til_tid=naa + timedelta(hours=1))
        c = self._med('alle2', [('statistikk', 'les'), ('vaktliste', 'les_alle')])
        self.assertNotIn('Hemmelig', json.dumps(c.get(self.KILDEN).json()))
