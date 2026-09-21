"""KO-fanen (statistikk pulje 7a, 21. sep. 2026): hendelsesbildet og loggen.

Reglene bor i `ko/statistikk.py`; hver funksjon prøves alene her, og fila
kjøres alene under mutasjonen. Tidene settes med `naa=`/`tidspunkt=` der
tjenestene tar det, og skrus ellers tilbake på raden — opprettelsen er
`auto_now_add`.
"""
from __future__ import annotations

import re
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.vakt import hent_aktiv_vakt
from ko import services, systemlinjer as sk
from ko.models import Hendelse, Logglinje
from ko.statistikk import ko_stats, lagperioder
from oppdrag import choices
from oppdrag import services as oservices
from oppdrag.models import Enhet, Lokasjon, Oppdrag
from vaktliste.models import Korps, Mannskap, Vaktliste, Vaktpost
from vaktliste.test_helpers import LAG, gruppe, lag_ressurs


def _bruker(navn, **kw):
    return CustomUser.objects.create_user(username=navn, password='x',
                                          must_change_password=False, **kw)


def _skift(ressurs):
    korps, _ = Korps.objects.get_or_create(navn='Testkorps')
    person, _ = Mannskap.objects.get_or_create(navn='Mannskap ' + ressurs.navn, korps=korps)
    naa = timezone.now()
    return Vaktpost.objects.create(ressurs=ressurs, mannskap=person,
                                   fra_tid=naa - timedelta(hours=6), til_tid=naa + timedelta(hours=6))


class Basis(TestCase):
    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.op = _bruker('ko1')
        self.enhet = Enhet.objects.create(navn='Ambulanse 1', pa_vakt=True)
        self.lokasjon = Lokasjon.objects.create(navn='Scene sør')
        self.vl = Vaktliste.objects.create(vakt=self.vakt)
        self.lag1 = lag_ressurs(vaktliste=self.vl, navn='Lag 1', gruppe=gruppe(LAG))
        self.lag2 = lag_ressurs(vaktliste=self.vl, navn='Lag 2', gruppe=gruppe(LAG))
        _skift(self.lag1); _skift(self.lag2)
        # Fast klokkeslett, så timebolkene er forutsigbare: 20:00 lokal i går.
        self.t0 = timezone.localtime(timezone.now()).replace(
            hour=20, minute=0, second=0, microsecond=0) - timedelta(days=1)
        self.naa = self.t0 + timedelta(hours=3)

    def _t(self, minutter):
        return self.t0 + timedelta(minutes=minutter)

    def _hendelse(self, tittel='Slagsmål', *, opprettet=0, prioritet='gul', **kw):
        h = services.opprett_hendelse(self.vakt, tittel, bruker=self.op,
                                      prioritet=prioritet, lokasjon=self.lokasjon, **kw)
        Hendelse.objects.filter(pk=h.pk).update(opprettet_at=self._t(opprettet))
        Logglinje.objects.filter(hendelse=h).update(tidspunkt=self._t(opprettet),
                                                    registrert_at=self._t(opprettet))
        h.refresh_from_db()
        return h

    def _lukk(self, h, minutter):
        return services.lukk_hendelse(h, bruker=self.op, confirm=True, naa=self._t(minutter))

    def _oppdrag(self, h=None, *, opprettet=0, enhet=None):
        o = Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=oservices.neste_oppdragsnummer(self.vakt),
            enhet=enhet or self.enhet, lokasjon=self.lokasjon, problemstilling='Fall',
            hastegrad='Haster')
        Oppdrag.objects.filter(pk=o.pk).update(created_at=self._t(opprettet))
        o.refresh_from_db()
        if h is not None:
            services.knytt_oppdrag(o, h, bruker=self.op, naa=self._t(opprettet))
        return o

    def _linje(self, tekst, minutter, *, h=None):
        linje = services.skriv_linje(self.vakt, tekst, bruker=self.op,
                                     tidspunkt=self._t(minutter), hendelse=h, naa=self._t(minutter))
        # `registrert_at` er auto_now_add; i prod er den skrivetidspunktet.
        Logglinje.objects.filter(pk=linje.pk).update(registrert_at=self._t(minutter))
        linje.refresh_from_db()
        return linje

    def stats(self):
        return ko_stats(self.vakt, naa=self.naa)


class HendelsesbildetTests(Basis):
    def test_antall_per_prioritet_lokasjon_og_melder(self):
        self._hendelse(prioritet='rod', melder_typer=['egen', 'politi'])
        self._hendelse(prioritet='gul', melder_typer=['andre'], melder='Vakt')
        h = self._hendelse(prioritet='gul'); self._lukk(h, 30)

        s = self.stats()['hendelser']
        self.assertEqual(s['antall'], 3)
        self.assertEqual(s['apne'], 2)
        self.assertEqual(list(s['per_prioritet']),
                         ['viktig', 'rod', 'gul', 'gronn', 'drift', 'plassering'])
        self.assertEqual(s['per_prioritet']['gul'], 2)
        self.assertEqual(s['per_lokasjon'], {'Scene sør': 3})
        # Flere meldere telles på hver av dem.
        self.assertEqual((s['per_melder']['egen'], s['per_melder']['politi'], s['per_melder']['andre']),
                         (1, 1, 1))
        self.assertEqual(s['varighet']['median'], 30.0)
        self.assertEqual(s['varighet']['n'], 1, 'åpne har ingen varighet ennå')
        self.assertEqual(s['varighet_per_prioritet']['gul']['median'], 30.0)


class ForsteRessursTests(Basis):
    def test_klokka_starter_ved_hendelsen(self):
        h = self._hendelse(prioritet='rod')
        services.sett_lag(h, [self.lag1.pk], bruker=self.op, naa=self._t(2))
        o = self._oppdrag(h, opprettet=5)
        oservices.sett_status(o, choices.RYKKER_UT, bruker=self.op, tidspunkt=self._t(7))

        t = self.stats()['tid_til_forste_ressurs']
        self.assertEqual(t['rod']['lag']['median'], 2.0)
        self.assertEqual(t['rod']['oppdrag']['median'], 5.0)
        self.assertEqual(t['rod']['rykker_ut']['median'], 7.0)
        self.assertEqual(t['rod']['ressurs']['median'], 2.0, 'det første av de tre')
        self.assertEqual(t['alle']['ressurs']['n'], 1)

    def test_oppdrag_knyttet_fra_for_hendelsen_teller_som_null(self):
        h = self._hendelse(opprettet=10)
        self._oppdrag(h, opprettet=3)
        self.assertEqual(self.stats()['tid_til_forste_ressurs']['gul']['oppdrag']['median'], 0.0)

    def test_alle_regnes_av_hendelsene_ikke_av_medianene(self):
        for prio, lag_min in (('rod', 1), ('gul', 5), ('gul', 9)):
            h = self._hendelse(prioritet=prio)
            services.sett_lag(h, [self.lag1.pk], bruker=self.op, naa=self._t(lag_min))
            services.sett_lag(h, [], bruker=self.op, naa=self._t(lag_min + 1))
        t = self.stats()['tid_til_forste_ressurs']
        self.assertEqual(t['alle']['ressurs']['median'], 5.0)
        self.assertEqual(t['alle']['ressurs']['n'], 3)

    def test_lag_fra_opprettelsen_teller_som_null(self):
        h = self._hendelse(lag=[self.lag1.pk])
        self.assertEqual(self.stats()['tid_til_forste_ressurs']['gul']['lag']['median'], 0.0)


class HvemLosteTests(Basis):
    def test_fire_ruter_uten_drift_og_plassering(self):
        a = self._hendelse(prioritet='gul', lag=[self.lag1.pk]); self._oppdrag(a, opprettet=4); self._lukk(a, 30)
        b = self._hendelse(prioritet='gul', lag=[self.lag1.pk]); self._lukk(b, 20)
        c = self._hendelse(prioritet='gronn'); self._oppdrag(c, opprettet=1); self._lukk(c, 20)
        d = self._hendelse(prioritet='gronn'); self._lukk(d, 5)
        e = self._hendelse(prioritet='drift'); self._lukk(e, 5)
        self._hendelse(prioritet='rod')   # åpen — telles ikke

        hl = self.stats()['hvem_loste']
        self.assertEqual(list(hl['per_prioritet']), ['viktig', 'rod', 'gul', 'gronn'])
        self.assertEqual(hl['per_prioritet']['gul'],
                         {'lag_og_oppdrag': 1, 'bare_lag': 1, 'bare_oppdrag': 0, 'verken': 0})
        self.assertEqual(hl['per_prioritet']['gronn'],
                         {'lag_og_oppdrag': 0, 'bare_lag': 0, 'bare_oppdrag': 1, 'verken': 1})
        self.assertEqual(hl['sum'], {'lag_og_oppdrag': 1, 'bare_lag': 1, 'bare_oppdrag': 1, 'verken': 1})
        self.assertEqual(hl['lag_til_oppdrag']['median'], 4.0)
        self.assertEqual(hl['verken_liste'], [], 'grønn listes ikke')

    def test_oppdrag_for_laget_gir_ingen_lag_til_oppdrag_tid(self):
        h = self._hendelse(prioritet='gul'); self._oppdrag(h, opprettet=1)
        services.sett_lag(h, [self.lag1.pk], bruker=self.op, naa=self._t(5))
        self._lukk(h, 20)
        hl = self.stats()['hvem_loste']
        self.assertEqual(hl['per_prioritet']['gul']['lag_og_oppdrag'], 1)
        self.assertEqual(hl['lag_til_oppdrag']['n'], 0)

    def test_rod_og_viktig_uten_ressurs_listes_med_navn(self):
        h = self._hendelse('Savnet barn', prioritet='viktig')
        self._linje('Funnet av vakter', 10, h=h)
        self._lukk(h, 17)
        r = self._hendelse(prioritet='rod'); self._lukk(r, 3)

        liste = self.stats()['hvem_loste']['verken_liste']
        self.assertEqual([v['prioritet'] for v in liste], ['viktig', 'rod'])
        self.assertEqual(liste[0]['tittel'], 'Savnet barn')
        self.assertEqual(liste[0]['minutter'], 17.0)
        self.assertEqual(liste[0]['lukket_av'], 'ko1')
        self.assertEqual(liste[0]['siste_linje'], 'Funnet av vakter')

    def test_fjernet_linje_er_ikke_siste_linje(self):
        h = self._hendelse(prioritet='rod')
        self._linje('Første', 1, h=h)
        l2 = self._linje('Feil person', 2, h=h)
        services.fjern(l2, bruker=self.op, naa=self._t(3))
        self._lukk(h, 5)
        self.assertEqual(self.stats()['hvem_loste']['verken_liste'][0]['siste_linje'], 'Første')

    def test_lag_som_ble_tatt_av_teller_fortsatt_som_lag(self):
        """Raden slettes; loggen står. Ellers ville «bare lag» blitt «verken»."""
        h = self._hendelse(prioritet='gul', lag=[self.lag1.pk])
        services.sett_lag(h, [], bruker=self.op, naa=self._t(10))
        self._lukk(h, 20)
        self.assertEqual(self.stats()['hvem_loste']['per_prioritet']['gul']['bare_lag'], 1)


class EskaleringTests(Basis):
    def test_matrise_opp_ned_og_tid(self):
        h = self._hendelse(prioritet='gul')
        services.sett_prioritet(h, 'rod', bruker=self.op, naa=self._t(9))
        services.sett_prioritet(h, 'gul', bruker=self.op, naa=self._t(40))
        g = self._hendelse(prioritet='gronn')
        services.sett_prioritet(g, 'gul', bruker=self.op, naa=self._t(3))

        e = self.stats()['eskaleringer']
        self.assertEqual(e['matrise']['gul']['rod'], 1)
        self.assertEqual(e['matrise']['rod']['gul'], 1)
        self.assertEqual(e['matrise']['gronn']['gul'], 1)
        self.assertEqual((e['opp'], e['ned']), (2, 1))
        self.assertEqual(e['etter_opprettelse']['median'], 9.0)

    def test_gjenapninger_telles(self):
        h = self._hendelse(); self._lukk(h, 5)
        services.gjenapne_hendelse(h, bruker=self.op, naa=self._t(6))
        self.assertEqual(self.stats()['gjenapninger'], 1)


class SamtidighetTests(Basis):
    def test_apne_per_time_med_hoyeste_prioritet(self):
        # Rød først, så gul: den sist behandlede er ikke den høyeste.
        r = self._hendelse(prioritet='rod', opprettet=70); self._lukk(r, 120)     # 21:10–22:00
        self._hendelse(prioritet='gul', opprettet=10)                            # 20:10 → åpen til nå (23:00)
        sam = {r['time']: r for r in self.stats()['samtidighet']}
        self.assertEqual((sam[20]['apne'], sam[20]['hoyeste']), (1, 'gul'))
        self.assertEqual((sam[21]['apne'], sam[21]['hoyeste']), (2, 'rod'))
        # Lukket nøyaktig 22:00: sto ikke åpen i time 22.
        self.assertEqual((sam[22]['apne'], sam[22]['hoyeste']), (1, 'gul'))
        self.assertEqual((sam[19]['apne'], sam[19]['hoyeste']), (0, None))


class LagperiodeTests(Basis):
    def test_periodene_leses_av_loggen(self):
        h = self._hendelse(lag=[self.lag1.pk])
        services.sett_lag(h, [self.lag1.pk, self.lag2.pk], bruker=self.op, naa=self._t(30))
        services.sett_lag(h, [self.lag2.pk], bruker=self.op, naa=self._t(60))      # lag 1 av
        services.sett_lag(h, [self.lag1.pk, self.lag2.pk], bruker=self.op, naa=self._t(90))  # lag 1 på igjen
        self._lukk(h, 120)
        h.refresh_from_db()
        perioder = sorted(lagperioder(h, list(Logglinje.objects.filter(hendelse=h).order_by('tidspunkt', 'id')),
                                      h.lukket_at))
        self.assertEqual(perioder, [
            ('Lag 1', self._t(0), self._t(60)),
            ('Lag 1', self._t(90), self._t(120)),
            ('Lag 2', self._t(30), self._t(120)),
        ])
        r = self.stats()['ressursbruk']
        self.assertEqual(r['lagtimer'], 3.0)
        self.assertEqual(r['per_lag']['Lag 1'], {'hendelser': 1, 'timer': 1.5})
        self.assertEqual(r['per_lag']['Lag 2'], {'hendelser': 1, 'timer': 1.5})

    def test_aapen_hendelse_regnes_til_naa(self):
        self._hendelse(lag=[self.lag1.pk])   # 20:00 → nå 23:00
        self.assertEqual(self.stats()['ressursbruk']['lagtimer'], 3.0)

    def test_oppdrag_per_hendelse(self):
        h = self._hendelse(); self._oppdrag(h); self._oppdrag(h, opprettet=1)
        self._hendelse()
        r = self.stats()['ressursbruk']
        self.assertEqual(r['oppdrag_per_hendelse']['max'], 2.0)
        self.assertEqual(r['hendelser_med_oppdrag'], 1)


class LoggTests(Basis):
    def test_linjer_per_time_rettinger_fjerninger_og_deling(self):
        h = self._hendelse()                                   # 20:00: systemlinje
        l1 = self._linje('Første', 5, h=h)                     # 20:05
        retting = services.korriger(l1, bruker=self.op, tekst='Første, rettet', naa=self._t(12))
        Logglinje.objects.filter(pk=retting.pk).update(registrert_at=self._t(12))
        l3 = self._linje('Feil', 70)                           # 21:10
        services.fjern(l3, bruker=self.op, naa=self._t(71))
        l4 = self._linje('Delt', 80, h=h)
        services.del_linje(l4, bruker=self.op, naa=self._t(83))

        l = self.stats()['logg']
        per = {r['time']: r for r in l['per_time']}
        self.assertEqual(per[20]['system'], 1)
        self.assertEqual(per[20]['operator'], 2, 'linja og rettingen av den')
        self.assertEqual(per[21]['operator'], 2)
        self.assertEqual(l['rettinger'], 1)
        self.assertEqual(l['tid_til_retting']['median'], 7.0)
        self.assertEqual(l['fjerninger'], 1)
        self.assertEqual((l['hendelseslinjer'], l['delte']), (2, 1))
        self.assertEqual(l['tid_til_deling']['median'], 3.0)

    def test_stemplinger_fort_av_ko_og_forsinkede(self):
        o = self._oppdrag()
        oservices.sett_status(o, choices.RYKKER_UT, bruker=self.op, tidspunkt=self._t(1), manuell=True)
        oservices.sett_status(o, choices.FREMME, bruker=self.op, tidspunkt=self._t(5), forsinket=True)
        oservices.sett_status(o, choices.AVREIST, bruker=self.op, tidspunkt=self._t(9), forsinket=True)
        st = self.stats()['stemplinger']
        self.assertEqual((st['antall'], st['ko_forte'], st['forsinkede']), (3, 1, 2))


class StillhetTests(Basis):
    def test_hullene_maales_bare_mens_noe_staar_apent(self):
        self._linje('Rolig', 0)
        self._linje('Fortsatt rolig', 50)                      # hull uten hendelse: ikke med
        h = self._hendelse(prioritet='rod', opprettet=60)
        self._linje('Melding', 61, h=h)
        self._linje('Neste', 84, h=h)                          # 23 min
        self._lukk(h, 90)
        g = self._hendelse(prioritet='gronn', opprettet=100)
        self._linje('Siste', 101, h=g)                         # → nå (23:00): 79 min, pågår

        hull = self.stats()['stillhet']
        # 84 → 101 telles også: hendelsen sto åpen da hullet begynte. Regelen
        # er «åpent ved start», ikke «åpent hele veien» — lukkingen skriver
        # ingen operatørlinje, og et hull som begynte i en åpen hendelse er
        # et hull.
        self.assertEqual([round(x['minutter']) for x in hull], [79, 23, 17])
        self.assertTrue(hull[0]['paagaar'])
        self.assertEqual((hull[1]['apne'], hull[1]['hoyeste'], hull[1]['paagaar']), (1, 'rod', False))

    def test_hullet_som_begynner_i_opprettelsen_teller(self):
        """Beskrivelsen skrives i samme øyeblikk som hendelsen opprettes."""
        h = self._hendelse(beskrivelse='Melding fra vakt')
        self._linje('Neste', 10, h=h)
        self._lukk(h, 10)
        self.assertEqual([x['minutter'] for x in self.stats()['stillhet']], [10.0])

    def test_hull_under_ett_minutt_er_ikke_hull(self):
        h = self._hendelse()
        self._linje('a', 1, h=h)
        services.skriv_linje(self.vakt, 'b', bruker=self.op, tidspunkt=self._t(1) + timedelta(seconds=20),
                             hendelse=h, naa=self._t(2))
        self._linje('c', 3, h=h)
        self._lukk(h, 3)
        self.assertEqual([x['minutter'] for x in self.stats()['stillhet']], [1.7])

    def test_tre_lengste(self):
        h = self._hendelse()
        for m in (0, 2, 5, 9, 14, 20):
            self._linje('x', m, h=h)
        self._lukk(h, 20)
        self.assertEqual([x['minutter'] for x in self.stats()['stillhet']], [6.0, 5.0, 4.0])


class FaneOgGateTests(TestCase):
    KILDEN = '/statistikk/api/kilde/ko/full-stats/'

    def _med(self, navn, tilganger):
        bruker = _bruker(navn)
        for modul, nivaa in tilganger:
            ModulTilgang.objects.update_or_create(bruker=bruker, modul_slug=modul,
                                                  defaults={'nivaa': nivaa})
        c = Client(); c.force_login(bruker); return c

    def test_handleren_er_registrert(self):
        from core.stats import get_handler
        self.assertEqual(get_handler('ko').display_name, 'KO')

    def test_uten_ko_tilgang_ingen_fane_og_403(self):
        c = self._med('kun_pasient', [('statistikk', 'les'), ('patients', 'les')])
        html = c.get('/statistikk/').content.decode('utf-8')
        self.assertNotIn('kilde-ko', html)
        self.assertNotRegex(html, r'statistikk-ko(\.[0-9a-f]{8,})?\.js')
        self.assertEqual(c.get(self.KILDEN).status_code, 403)

    def test_med_ko_tilgang_kommer_fane_fil_og_tall(self):
        c = self._med('ko_leser', [('statistikk', 'les'), ('ko', 'les')])
        html = c.get('/statistikk/').content.decode('utf-8')
        self.assertIn('kilde-ko', html)
        self.assertRegex(html, r'statistikk-ko(\.[0-9a-f]{8,})?\.js')
        svar = c.get(self.KILDEN)
        self.assertEqual(svar.status_code, 200)
        self.assertIn('hvem_loste', svar.json())

    def test_ingen_arkivstatistikk_for_ko(self):
        c = self._med('ko_admin', [('statistikk', 'les'), ('ko', 'les')])
        c = Client(); c.force_login(_bruker('adm', role='admin'))
        self.assertEqual(c.get('/statistikk/api/kilde/ko/arkiv/1/full-stats/').status_code, 404)

    def test_statistikk_js_kaller_ikke_ko_fila_direkte(self):
        """Samme vern som for oppdragsfila: kall går gjennom `_kallOppdrag()`."""
        from patients import js_test_utils as jsu
        ko_navn = set(re.findall(r'^(?:async )?function (\w+)', jsu.read_js(jsu.STATISTIKK_KO_JS), re.M))
        self.assertIn('loadKoStats', ko_navn)
        kilde = '\n'.join(l for l in jsu.read_js(jsu.STATISTIKK_JS).splitlines()
                          if not l.lstrip().startswith('//'))
        kilde = re.sub(r"_kallOppdrag\(\s*'[^']+'", '_kallOppdrag(', kilde)
        funn = [n for n in sorted(ko_navn) if re.search(r'\b' + re.escape(n) + r'\s*\(', kilde)]
        self.assertEqual(funn, [])

    def test_ko_fila_bruker_bare_det_siden_laster(self):
        """Ingen kall inn i statistikk-oppdrag.js — den lastes uten KO-tilgang,
        og KO-fila kan lastes uten oppdragstilgang."""
        from patients import js_test_utils as jsu
        oppdrag_navn = set(re.findall(r'^(?:async )?function (\w+)',
                                      jsu.read_js(jsu.STATISTIKK_OPPDRAG_JS), re.M))
        kilde = '\n'.join(l for l in jsu.read_js(jsu.STATISTIKK_KO_JS).splitlines()
                          if not l.lstrip().startswith('//'))
        funn = [n for n in sorted(oppdrag_navn) if re.search(r'\b' + re.escape(n) + r'\s*\(', kilde)]
        self.assertEqual(funn, [])
