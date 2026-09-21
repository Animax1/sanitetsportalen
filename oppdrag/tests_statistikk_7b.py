"""Statistikk pulje 7b (21. sep. 2026): ventetida i to, køen, hvem løste hva.

Egen fil framfor 300 linjer til i `tests_statistikk.py`: reglene her er nye
funksjoner (`_ventetid_og_koe`, `_konkordans`, …), og de skal kunne kjøres
alene under mutasjonen — `oppdrag.tests_statistikk_7b` er sekunder,
`oppdrag` er 40.

**Fiksturen bærer prod-formen**: `varslet_at` settes eksplisitt på hver
koblingsrad. `Oppdrag.save()` setter den til nå, og med `created_at` skrudd
tilbake ville hver reaksjonstid vært negativ og hver KO-ventetid en time.
"""
from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from patients.test_helpers import sett_aktiv_vakt

from . import choices, services
from .arkiv import OppdragArkivHandler, arkiver_vakt
from .models import ArkivertOppdrag, Enhet, Enhetshendelse, Enhetstype, Lokasjon, Oppdrag
from .statistikk import (_i_hastegradrekkefolge, _p90, _sd, _timebolker,
                         arkiv_stats, oppdrag_stats)

AAR = 2096


class Basis(TestCase):
    def setUp(self):
        self.vakt = sett_aktiv_vakt(AAR)
        self.lokasjon = Lokasjon.objects.create(navn='Hovedscene')
        # Avventing krever et flagg på enhetstypen (`kan_avvente`).
        typen = Enhetstype.objects.create(navn='Testbil', kan_avvente=True)
        self.a1 = Enhet.objects.create(navn='Ambulanse 1', pa_vakt=True, enhetstype=typen)
        self.a2 = Enhet.objects.create(navn='Ambulanse 2', pa_vakt=True, enhetstype=typen)
        self.bruker = CustomUser.objects.create_user(
            username='sentral', password='x', must_change_password=False)
        # Et fast klokkeslett, så timebolkene er forutsigbare: 20:00 lokal.
        self.t0 = timezone.localtime(timezone.now()).replace(
            hour=20, minute=0, second=0, microsecond=0) - timedelta(days=1)

    def _t(self, minutter):
        return self.t0 + timedelta(minutes=minutter)

    def _oppdrag(self, *, enhet='a1', hastegrad='Akutt', problemstilling='Pustevansker',
                 opprettet=0, varslet=None, **felter):
        enhet = getattr(self, enhet) if isinstance(enhet, str) else enhet
        oppdrag = Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=services.neste_oppdragsnummer(self.vakt),
            enhet=enhet, problemstilling=problemstilling, hastegrad=hastegrad,
            lokasjon=self.lokasjon, **felter)
        Oppdrag.objects.filter(pk=oppdrag.pk).update(created_at=self._t(opprettet))
        oppdrag.enheter.update(
            varslet_at=self._t(opprettet if varslet is None else varslet))
        oppdrag.refresh_from_db()
        return oppdrag

    def _varsle(self, oppdrag, enhet, minutter):
        rad = services.varsle_enhet(oppdrag, enhet, bruker=self.bruker)
        rad.varslet_at = self._t(minutter)
        rad.save(update_fields=['varslet_at'])
        return rad

    def _stempel(self, oppdrag, status, minutter, *, enhet=None, **kw):
        return services.sett_status(oppdrag, status, bruker=self.bruker,
                                    tidspunkt=self._t(minutter), enhet=enhet, **kw)

    def _rykk(self, oppdrag, minutter, enhet=None):
        return services.start_oppdrag(oppdrag, bruker=self.bruker,
                                      tidspunkt=self._t(minutter), enhet=enhet)

    def stats(self):
        return oppdrag_stats(self.vakt)


class SammendragTests(TestCase):
    def test_p90_er_naermeste_rang(self):
        self.assertEqual(_p90([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), 9)
        self.assertEqual(_p90([5]), 5)
        self.assertEqual(_p90([3, 1, 2]), 3)

    def test_sd_baerer_p90(self):
        self.assertEqual(_sd([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])['p90'], 9.0)
        self.assertIsNone(_sd([])['p90'])

    def test_hastegradene_i_amk_rekkefolge_med_nuller(self):
        """C8: alle fem, i fast rekkefølge, også de på null. Ukjente sist."""
        self.assertEqual(
            list(_i_hastegradrekkefolge({'Vanlig': 3, 'Akutt': 1, 'Gammel': 2}).items()),
            [('Akutt', 1), ('Haster', 0), ('Vanlig', 3), ('Drift', 0),
             ('Plassering', 0), ('Gammel', 2)])

    def test_timebolker(self):
        t0 = timezone.localtime(timezone.now()).replace(hour=20, minute=0, second=0, microsecond=0)
        antall, lengste = _timebolker(
            [(t0 + timedelta(minutes=50), t0 + timedelta(minutes=70)),
             (t0 + timedelta(minutes=55), None)],
            naa=t0 + timedelta(minutes=125))
        self.assertEqual((antall[20], antall[21], antall[22]), (2, 2, 1))
        # Ved 21:00 hadde den første ventet 10 min og den andre 5.
        self.assertEqual(lengste[20], 10.0)
        # Ved 22:00: den åpne hadde ventet 65 min; den første sluttet 21:10 (20 min).
        self.assertEqual(lengste[21], 65.0)
        self.assertEqual(lengste[22], 70.0)
        self.assertEqual(antall[19], 0)


class VentetidDeltTests(Basis):
    def test_ko_ventetid_og_reaksjonstid_er_to_tall(self):
        """Opprettet uten enhet kl. 0, varslet +6, rykker ut +9."""
        o = self._oppdrag(enhet=None, trenger_ressurs=True)
        self._varsle(o, self.a1, 6)
        self._rykk(o, 9, self.a1)

        vd = self.stats()['ventetid_delt']
        self.assertEqual(vd['ko_ventetid']['median'], 6.0)
        self.assertEqual(vd['reaksjonstid']['median'], 3.0)
        self.assertEqual(vd['per_hastegrad']['Akutt']['ko_ventetid']['n'], 1)
        self.assertEqual(vd['per_hastegrad']['Akutt']['reaksjonstid']['median'], 3.0)
        self.assertEqual(vd['reaksjonstid_per_enhet']['Ambulanse 1']['median'], 3.0)
        # Summen er dagens ventetid — ingenting går tapt.
        self.assertEqual(self.stats()['summary']['ventetid']['median'], 9.0)

    def test_opprettet_med_enhet_gir_null_ko_ventetid(self):
        o = self._oppdrag()
        self._rykk(o, 2)
        vd = self.stats()['ventetid_delt']
        self.assertEqual(vd['ko_ventetid']['median'], 0.0)
        self.assertEqual(vd['reaksjonstid']['median'], 2.0)

    def test_per_hastegrad_har_alle_fem(self):
        """C8 — i alle tre tabellene som går per hastegrad."""
        self._oppdrag(hastegrad='Vanlig')
        s = self.stats()
        for nokkel in ('per_hastegrad', 'responstid_per_hastegrad'):
            self.assertEqual(list(s[nokkel]), list(choices.HASTEGRAD), nokkel)
        self.assertEqual(list(s['ventetid_delt']['per_hastegrad']), list(choices.HASTEGRAD))
        self.assertEqual(s['per_hastegrad']['Akutt'], 0)

    def test_avbrutt_starter_ny_ko_ventetid(self):
        """Bilen avbryter +10, ny bil varsles +25: KO-ventetid 15, og
        oppdraget telles som «stående uten ressurs etter avgang»."""
        o = self._oppdrag()
        self._rykk(o, 2)
        services.avbryt_oppdrag(o, bruker=self.bruker, tidspunkt=self._t(10), enhet=self.a1)
        self._varsle(o, self.a2, 25)

        vd = self.stats()['ventetid_delt']
        self.assertEqual(sorted(v for v in [vd['ko_ventetid']['min'], vd['ko_ventetid']['max']]),
                         [0.0, 15.0])
        self.assertEqual(vd['ko_ventetid']['n'], 2)
        self.assertEqual(vd['uten_ressurs_etter_avgang'], 1)

    def test_forsterkning_er_ikke_ventetid(self):
        """Bil to varsles mens bil én er på vei: ingen ny KO-ventetid."""
        o = self._oppdrag()
        self._rykk(o, 2)
        self._varsle(o, self.a2, 5)
        vd = self.stats()['ventetid_delt']
        self.assertEqual(vd['ko_ventetid']['n'], 1)
        self.assertEqual(vd['ko_ventetid']['max'], 0.0)
        self.assertEqual(vd['uten_ressurs_etter_avgang'], 0)

    def test_avbrutt_mens_en_annen_er_paa_vei_er_ikke_uten_ressurs(self):
        """Samme regel som `trenger_ny_ressurs`: står noen igjen, ventes det ikke."""
        o = self._oppdrag()
        self._rykk(o, 2)
        self._varsle(o, self.a2, 3)
        self._rykk(o, 4, self.a2)
        services.avbryt_oppdrag(o, bruker=self.bruker, tidspunkt=self._t(10), enhet=self.a1)
        self.assertEqual(self.stats()['ventetid_delt']['uten_ressurs_etter_avgang'], 0)

    def test_en_annen_som_meldte_ledig_i_samme_oyeblikk_er_ikke_aktiv(self):
        """Kanten: bil to melder ledig kl. 10, bil én avbryter kl. 10."""
        o = self._oppdrag()
        self._rykk(o, 2)
        self._varsle(o, self.a2, 3)
        self._rykk(o, 4, self.a2)
        self._stempel(o, choices.LEDIG, 10, enhet=self.a2)
        services.avbryt_oppdrag(o, bruker=self.bruker, tidspunkt=self._t(10), enhet=self.a1)
        self.assertEqual(self.stats()['ventetid_delt']['uten_ressurs_etter_avgang'], 1)

    def test_avventing_slutter_naar_hun_selv_rykker_ut(self):
        """Ingen ny varsles; hun ombestemmer seg. Ventetida er avvent → rykk."""
        o = self._oppdrag()
        services.avvent_oppdrag(o, self.a1, bruker=self.bruker, tidspunkt=self._t(3))
        self._rykk(o, 11)
        vd = self.stats()['ventetid_delt']
        self.assertEqual(vd['ko_ventetid']['max'], 8.0)

    def test_passiv_vakt_holdes_utenfor(self):
        o = self._oppdrag()
        o.enheter.update(varslet_modus='passiv')
        self._rykk(o, 12)
        vd = self.stats()['ventetid_delt']
        self.assertEqual(vd['reaksjonstid']['n'], 0)
        self.assertEqual(vd['reaksjonstid_passiv']['median'], 12.0)
        self.assertNotIn('Ambulanse 1', vd['reaksjonstid_per_enhet'])

    def test_negativ_reaksjonstid_telles_som_utelatt(self):
        o = self._oppdrag(varslet=5)
        self._rykk(o, 2)
        s = self.stats()
        self.assertEqual(s['ventetid_delt']['reaksjonstid']['n'], 0)
        self.assertEqual(s['summary']['utelatt']['negativ'], 1)


class AldriRykketUtTests(Basis):
    def test_tatt_av_med_staatid(self):
        o = self._oppdrag()
        self._varsle(o, self.a2, 4)
        # Hendelsen får tidspunktet nå; sett det for at ståtida skal bli 6.
        services.ta_av_enhet(o, self.a2, bruker=self.bruker)
        Enhetshendelse.objects.filter(type=Enhetshendelse.TATT_AV).update(tidspunkt=self._t(10))

        s = self.stats()
        liste = s['aldri_rykket_ut']
        self.assertEqual(len(liste), 1)
        self.assertEqual((liste[0]['enhet'], liste[0]['sto_i'], liste[0]['endte']),
                         ('Ambulanse 2', 6.0, 'Tatt av'))
        # Hun sto i køen som «tildelt, venter» fra 20:04 til 20:10 — sammen
        # med bil én, som fortsatt venter.
        koe = {k['time']: k for k in s['koe']}
        self.assertEqual(koe[20]['tildelt_venter'], 2)

    def test_tatt_av_baerer_varslingstida(self):
        """Raden slettes; hendelsen må huske når hun ble varslet (0030)."""
        o = self._oppdrag()
        rad = self._varsle(o, self.a2, 4)
        services.ta_av_enhet(o, self.a2, bruker=self.bruker)
        h = Enhetshendelse.objects.get(type=Enhetshendelse.TATT_AV)
        self.assertEqual(h.varslet_at, rad.varslet_at)

    def test_avbrutt_avventer_og_rykket_videre_baerer_varslingstida(self):
        o = self._oppdrag()
        services.avvent_oppdrag(o, self.a1, bruker=self.bruker, tidspunkt=self._t(1))
        self._rykk(o, 2)
        services.avbryt_oppdrag(o, bruker=self.bruker, tidspunkt=self._t(5), enhet=self.a1)
        annet = self._oppdrag(opprettet=6)
        self._rykk(annet, 7)
        tredje = self._oppdrag(enhet=None, opprettet=8, trenger_ressurs=True)
        self._varsle(tredje, self.a1, 8)
        self._rykk(tredje, 9, self.a1)   # rykker videre fra `annet`
        typer = {h.type: h.varslet_at for h in Enhetshendelse.objects.all()}
        self.assertEqual(typer[Enhetshendelse.AVVENTER], self._t(0))
        self.assertEqual(typer[Enhetshendelse.AVBRUTT], self._t(0))
        self.assertEqual(typer[Enhetshendelse.RYKKET_VIDERE], self._t(6))

    def test_meldt_ledig_uten_aa_rykke_ut(self):
        o = self._oppdrag()
        self._stempel(o, choices.LEDIG, 7)
        liste = self.stats()['aldri_rykket_ut']
        self.assertEqual((liste[0]['sto_i'], liste[0]['endte']),
                         (7.0, 'Meldt ledig uten å rykke ut'))

    def test_den_som_rykket_ut_er_ikke_med(self):
        o = self._oppdrag()
        self._rykk(o, 3)
        self.assertEqual(self.stats()['aldri_rykket_ut'], [])


class KoeTests(Basis):
    def test_koen_per_time_og_toppene(self):
        # Uten ressurs 20:00–20:30 (varslet 20:30), venter 20:30–20:45.
        o = self._oppdrag(enhet=None, trenger_ressurs=True)
        self._varsle(o, self.a1, 30)
        self._rykk(o, 45, self.a1)
        # Et til, tildelt ved opprettelsen 21:10, rykker ut 21:20. Til bil to:
        # bil én står fortsatt i Rykker ut på det første, og ville rykket
        # videre — og da sto det første uten ressurs fra 21:20.
        p = self._oppdrag(opprettet=70, hastegrad='Vanlig', enhet='a2')
        self._rykk(p, 80, self.a2)

        s = self.stats()
        koe = {k['time']: k for k in s['koe']}
        self.assertEqual((koe[20]['uten_ressurs'], koe[20]['tildelt_venter']), (1, 1))
        self.assertEqual((koe[21]['uten_ressurs'], koe[21]['tildelt_venter']), (0, 1))
        self.assertEqual(koe[20]['lengste'], 30.0)
        self.assertEqual(koe[21]['lengste'], 10.0)
        self.assertEqual(s['flest_i_koe'], {'antall': 2, 'time': 20})
        self.assertEqual(s['lengste_uten_ressurs']['minutter'], 30.0)
        self.assertEqual(s['lengste_uten_ressurs']['oppdragsnummer'], o.oppdragsnummer)
        self.assertFalse(s['lengste_uten_ressurs']['paagaar'])

    def test_staar_fortsatt_uten_ressurs(self):
        self._oppdrag(enhet=None, trenger_ressurs=True, opprettet=0)
        s = self.stats()
        self.assertTrue(s['lengste_uten_ressurs']['paagaar'])
        # Åpent intervall telles ikke i KO-ventetida — den er ikke målt ennå.
        self.assertEqual(s['ventetid_delt']['ko_ventetid']['n'], 0)

    def test_tom_vakt(self):
        s = self.stats()
        self.assertIsNone(s['flest_i_koe'])
        self.assertIsNone(s['lengste_uten_ressurs'])
        self.assertEqual(len(s['koe']), 24)


class KonkordansTests(Basis):
    def test_krysstabell_og_avvik(self):
        self._oppdrag(hastegrad='Akutt', grovsortering='rod')
        self._oppdrag(hastegrad='Akutt', grovsortering='gronn')      # bilen lavere
        self._oppdrag(hastegrad='Vanlig', grovsortering='rod')       # bilen høyere
        self._oppdrag(hastegrad='Haster', grovsortering='rod')       # bilen høyere
        self._oppdrag(hastegrad='Haster', grovsortering='ikke_aktuelt')
        self._oppdrag(hastegrad='Haster')                            # ikke vurdert
        self._oppdrag(hastegrad='Drift', grovsortering='rod')        # utenfor

        k = self.stats()['konkordans']
        self.assertEqual(k['rader'], ['Akutt', 'Haster', 'Vanlig'])
        self.assertEqual(k['antall']['Akutt'], {'rod': 1, 'gul': 0, 'gronn': 1, 'ikke_aktuelt': 0, '': 0})
        self.assertEqual(k['antall']['Haster'], {'rod': 1, 'gul': 0, 'gronn': 0, 'ikke_aktuelt': 1, '': 1})
        # Asymmetrisk med vilje: 1 og 1 lot en mutant bytte om de to.
        self.assertEqual((k['vurderte'], k['enige'], k['bilen_hoyere'], k['bilen_lavere']),
                         (4, 1, 2, 1))
        self.assertEqual(k['kolonner'][-1], ['', 'Ikke vurdert'])

    def test_telles_en_gang_per_oppdrag(self):
        o = self._oppdrag(grovsortering='rod')
        self._varsle(o, self.a2, 1)
        self.assertEqual(self.stats()['konkordans']['vurderte'], 1)


class AvreistOgUtfallTests(Basis):
    def test_avreist_til_per_sted_og_annet_tekst(self):
        o = self._oppdrag()
        self._rykk(o, 1); self._stempel(o, choices.FREMME, 3)
        self._stempel(o, choices.AVREIST, 10, sted='sykehus')
        p = self._oppdrag(hastegrad='Vanlig')
        self._rykk(p, 1); self._stempel(p, choices.FREMME, 3)
        self._stempel(p, choices.AVREIST, 12, sted='annet', sted_tekst='Hotell Maritim')
        self._oppdrag(hastegrad='Haster')   # ikke avreist — skal ikke telles som et sted

        a = self.stats()['avreist_til']
        self.assertNotIn('(ikke oppgitt)', a['per_sted'])
        self.assertEqual(a['per_sted']['Sykehus'], 1)
        self.assertEqual(a['per_sted']['Annet sted'], 1)
        self.assertEqual(a['per_sted']['Legevakt'], 0)
        self.assertEqual(a['per_sted_hastegrad']['Sykehus'], {'Akutt': 1})
        self.assertEqual(a['annet_tekster'], [
            {'oppdragsnummer': p.oppdragsnummer, 'enhet': 'Ambulanse 1', 'tekst': 'Hotell Maritim'}])

    def test_utfall_per_problemstilling(self):
        a = self._oppdrag(problemstilling='Sår')
        self._rykk(a, 1); self._stempel(a, choices.FREMME, 3)
        services.behandle_paa_sted(a, bruker=self.bruker, tidspunkt=self._t(9))
        b = self._oppdrag(problemstilling='Sår')
        self._rykk(b, 1); self._stempel(b, choices.FREMME, 3)
        self._stempel(b, choices.AVREIST, 10, sted='legevakt')
        self._oppdrag(problemstilling='Rus')
        # To biler: én behandlet på sted, én kjørte. Pasienten ble transportert.
        c = self._oppdrag(problemstilling='Sår')
        self._rykk(c, 1); self._stempel(c, choices.FREMME, 3)
        services.behandle_paa_sted(c, bruker=self.bruker, tidspunkt=self._t(9), enhet=self.a1)
        self._varsle(c, self.a2, 2)
        self._rykk(c, 4, self.a2); self._stempel(c, choices.FREMME, 6, enhet=self.a2)
        self._stempel(c, choices.AVREIST, 12, sted='sykehus', enhet=self.a2)

        u = self.stats()['utfall_per_problemstilling']
        self.assertEqual(list(u), ['Sår', 'Rus'])
        self.assertEqual(u['Sår'], {'behandlet': 1, 'transportert': 2, 'uten': 0})
        self.assertEqual(u['Rus'], {'behandlet': 0, 'transportert': 0, 'uten': 1})

    def test_enhetshendelser_per_enhet(self):
        o = self._oppdrag()
        self._varsle(o, self.a2, 1)
        services.ta_av_enhet(o, self.a2, bruker=self.bruker)
        services.avvent_oppdrag(o, self.a1, bruker=self.bruker, tidspunkt=self._t(2))
        h = self.stats()['enhetshendelser']
        self.assertEqual(h['per_type'], {'tatt_av': 1, 'rykket_videre': 0, 'avbrutt': 0, 'avventer': 1})
        self.assertEqual(h['per_enhet']['Ambulanse 2']['tatt_av'], 1)
        self.assertEqual(h['per_enhet']['Ambulanse 1']['avventer'], 1)


class ArkivTests(Basis):
    def setUp(self):
        super().setUp()
        self.admin = CustomUser.objects.create_superuser(
            username='arkivadmin', password='x', role='admin', must_change_password=False)

    def _vakt_med_alt(self):
        o = self._oppdrag(enhet=None, trenger_ressurs=True, grovsortering='gul')
        self._varsle(o, self.a1, 6)
        self._rykk(o, 9, self.a1)
        self._stempel(o, choices.FREMME, 12, enhet=self.a1)
        self._stempel(o, choices.AVREIST, 20, sted='annet', sted_tekst='Hotell Maritim',
                      enhet=self.a1)
        self._varsle(o, self.a2, 7)
        services.ta_av_enhet(o, self.a2, bruker=self.bruker)
        return o

    def test_de_nye_tallene_er_de_samme_i_arkivet(self):
        self._vakt_med_alt()
        live = oppdrag_stats(self.vakt)
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        frosset = arkiv_stats(arkiv)
        for nokkel in ('ventetid_delt', 'koe', 'lengste_uten_ressurs', 'flest_i_koe',
                       'aldri_rykket_ut', 'konkordans', 'utfall_per_problemstilling',
                       'enhetshendelser', 'per_hastegrad', 'responstid_per_hastegrad'):
            with self.subTest(nokkel=nokkel):
                self.assertEqual(live[nokkel], frosset[nokkel])
        # Stedet fryses, teksten ikke.
        self.assertEqual(frosset['avreist_til']['per_sted'], live['avreist_til']['per_sted'])
        self.assertEqual(frosset['avreist_til']['annet_tekster'], [])
        self.assertEqual(len(live['avreist_til']['annet_tekster']), 1)

    def test_kolonnene_fryses_og_teksten_ikke(self):
        self._vakt_med_alt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        rad = ArkivertOppdrag.objects.get(enhet_navn='Ambulanse 1')
        self.assertEqual(rad.varslet_at, self._t(6))
        self.assertEqual((rad.grovsortering, rad.avreist_til), ('gul', 'annet'))
        self.assertEqual([h['type'] for h in rad.enhetshendelser], ['tatt_av'])
        # ISO-strengen er i UTC; sammenlign tidspunktet, ikke teksten.
        self.assertEqual(datetime.fromisoformat(rad.enhetshendelser[0]['varslet_at']), self._t(7))
        felter = {f.name for f in ArkivertOppdrag._meta.get_fields()}
        self.assertNotIn('avreist_til_tekst', felter)
        import json
        self.assertNotIn('Maritim', json.dumps(OppdragArkivHandler().rad_dicts(arkiv)))

    def test_payloaden_baerer_feltene_bare_naar_satt(self):
        """Et arkiv fra før 7b har ingen av dem — og skal verifisere uendret."""
        self._oppdrag()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        ArkivertOppdrag.objects.update(varslet_at=None, grovsortering='', avreist_til='',
                                       enhetshendelser=[])
        data = OppdragArkivHandler().rad_dicts(arkiv)[0]
        for nokkel in ('varslet_at', 'grovsortering', 'avreist_til', 'enhetshendelser'):
            self.assertNotIn(nokkel, data)

    def test_payloaden_baerer_feltene_naar_satt(self):
        self._vakt_med_alt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        data = OppdragArkivHandler().rad_dicts(arkiv)[0]
        self.assertEqual(data['grovsortering'], 'gul')
        self.assertEqual(data['avreist_til'], 'annet')
        self.assertEqual(datetime.fromisoformat(data['varslet_at']), self._t(6))
        self.assertEqual(data['enhetshendelser'][0]['type'], 'tatt_av')

    def test_aapent_intervall_slutter_ved_arkiveringen(self):
        """Ikke ved «nå», som kan være to år senere."""
        self._oppdrag(enhet=None, trenger_ressurs=True)
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        # Flytt arkiveringen til et tidspunkt som ikke er «nå» — ellers er
        # de to like innenfor avrundingen, og regelen står uprøvd.
        type(arkiv).objects.filter(pk=arkiv.pk).update(importert_at=self._t(30))
        arkiv.refresh_from_db()
        self.assertEqual(arkiv_stats(arkiv)['lengste_uten_ressurs']['minutter'], 30.0)


class KonkordansMarkupTests(TestCase):
    """Fargene i krysstabellen er en regel i markupen: grønn diagonal, rød
    der bilen fant det mer alvorlig, gul der hun fant det mindre."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from patients.js_test_utils import (PORTAL_UTILS_JS, STATISTIKK_OPPDRAG_JS,
                                            build_harness)
        cls.harness = build_harness((
            (PORTAL_UTILS_JS, ('escHtmlValue',)),
            (STATISTIKK_OPPDRAG_JS, ('mkKonkordansTabell',)),
        ))

    def _html(self, data):
        import json
        from patients.js_test_utils import run_node
        return run_node(self.harness, f'process.stdout.write(mkKonkordansTabell({json.dumps(data)}));')

    def test_fargene_folger_avviket(self):
        html = self._html({
            'rader': ['Akutt', 'Haster', 'Vanlig'],
            'kolonner': [['rod', 'Rød'], ['gul', 'Gul'], ['gronn', 'Grønn'],
                         ['ikke_aktuelt', 'Ikke aktuelt'], ['', 'Ikke vurdert']],
            'antall': {'Akutt': {'rod': 1, 'gul': 0, 'gronn': 2, 'ikke_aktuelt': 0, '': 0},
                       'Haster': {'rod': 0, 'gul': 0, 'gronn': 0, 'ikke_aktuelt': 0, '': 0},
                       'Vanlig': {'rod': 3, 'gul': 0, 'gronn': 0, 'ikke_aktuelt': 4, '': 0}},
            'vurderte': 6, 'enige': 1, 'bilen_hoyere': 3, 'bilen_lavere': 2,
        })
        import re
        celler = re.findall(r'<td class="([a-z-]*)">(\d+)</td>', html)
        self.assertIn(('heat-lo', '1'), celler)    # Akutt × rød: enige
        self.assertIn(('heat-mid', '2'), celler)   # Akutt × grønn: bilen lavere
        self.assertIn(('heat-hi', '3'), celler)    # Vanlig × rød: bilen høyere
        self.assertIn(('', '4'), celler)           # ikke aktuelt: ingen farge
        self.assertNotIn(('heat-hi', '0'), celler)

    def test_kolonnenavn_escapes(self):
        html = self._html({'rader': ['Akutt'], 'kolonner': [['rod', '<img src=x onerror=alert(1)>']],
                           'antall': {'Akutt': {'rod': 1}}, 'vurderte': 1, 'enige': 1,
                           'bilen_hoyere': 0, 'bilen_lavere': 0})
        self.assertNotIn('<img', html)
        self.assertIn('&lt;img', html)
