"""KO på papir, `/ko/utskrift/` (13. okt. 2026) — `ko/utskrift.py`, og kopien
uten nett i `/ko/sw.js`.

Papiret er reserven når portalen er borte midt i en vakt. Det som skal holde:

1. **Alle vinduene, alltid** — de åpne hendelsene, ressursene med besetning,
   de aktive oppdragene, tavla slik den står, konsertene som pågår og kommer,
   og loggen de siste åtte timene. Ingen valg.
2. **Samme fortelling som skjermen** — loggen i `gjeldende()` sin rekkefølge,
   med kommentarene i hendelsene som strømmen skjuler.
3. **Hver del har sin moduls gate** — en del man mangler tilgang til står som
   en setning, og resten skrives ut.
4. **Kopien uten nett er bare for personlige kontoer** — serveren merker
   svaret, og workeren lagrer ingenting umerket.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_tz
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from ko import services, systemlinjer, tavle
from ko.models import Logglinje
from ko.utskrift import KOPI_HODE, LOGG_TIMER
from oppdrag import choices
from oppdrag import services as oservices
from oppdrag.models import Oppdrag

from patients.js_test_utils import JS_DIR, build_harness, extract_function, node_available, run_node

from .tests_hendelseslogg import _gi, skift
from .tests_program import _Program

URL = '/ko/utskrift/'
SW_JS = JS_DIR / 'ko-sw.js'


def _html(svar):
    return ' '.join(svar.content.decode().split())


def _del(html, overskrift):
    """Bare delen under `<h2>overskrift…` — fram til neste `<h2>`. Alle delene
    står på samme side, og loggen har systemlinjer om de samme oppdragene og
    flyttingene: uten avgrensning finner en test for tavla navnet i loggen."""
    start = html.index('<h2>' + overskrift)
    slutt = html.find('<h2>', start + 4)
    return html[start:slutt if slutt != -1 else len(html)]


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class _Utskrift(_Program):

    def setUp(self):
        super().setUp()
        for modul in ('ko', 'vaktliste', 'oppdrag'):
            _gi(self.operator, modul, 'les')
        _gi(self.operator, 'ko', 'skriv_full')
        self.klient = Client()
        self.klient.force_login(self.operator)

    def _hent(self):
        svar = self.klient.get(URL)
        self.assertEqual(svar.status_code, 200)
        return _html(svar)


class PorteneTests(_Utskrift):

    def test_anonym_sendes_til_innlogging(self):
        svar = Client().get(URL)
        self.assertEqual(svar.status_code, 302)
        self.assertIn('/accounts/login/', svar['Location'])

    def test_uten_ko_rad_stengt(self):
        uten = CustomUser.objects.create_user(username='uten', password='x', must_change_password=False)
        klient = Client()
        klient.force_login(uten)
        self.assertEqual(klient.get(URL).status_code, 403)

    def test_tar_ikke_imot_skriving(self):
        self.assertEqual(self.klient.post(URL).status_code, 405)

    def test_bare_ko_gir_de_andre_delene_som_en_setning(self):
        ModulTilgang.objects.filter(bruker=self.operator).exclude(modul_slug='ko').delete()
        html = self._hent()
        self.assertIn('Oppdragene krever lesetilgang i oppdragsmodulen.', html)
        self.assertIn('Tavla viser vaktlistas ressurser, og krever lesetilgang i vaktlista.', html)
        self.assertIn('Ressursoversikten krever lesetilgang i oppdragsmodulen eller vaktlista.', html)
        self.assertIn('Ingen åpne hendelser.', html, 'KOs egne deler står')

    def test_med_tilgang_ingen_setning(self):
        html = self._hent()
        self.assertNotIn('krever lesetilgang', html)

    def test_alle_vinduene_alltid_i_vinduenes_rekkefolge(self):
        html = self._hent()
        overskrifter = ['<h2>Åpne hendelser</h2>', '<h2>Ressursoversikten</h2>', '<h2>Aktive oppdrag</h2>',
                        '<h2>Tavla</h2>', '<h2>Konsertplanleggeren', '<h2>Loggen']
        plass = [html.index(o) for o in overskrifter]
        self.assertEqual(plass, sorted(plass))
        self.assertNotIn('name="vis"', html, 'ingen valg av deler')

    def test_en_knapp_i_verktoylinja(self):
        html = _html(self.klient.get('/ko/'))
        self.assertEqual(html.count(f'href="{URL}"'), 1)
        self.assertNotIn(f'{URL}?vis=', html)


class HendelseneTests(_Utskrift):

    def test_bare_de_aapne_men_loggen_har_den_lukkede(self):
        aapen = services.opprett_hendelse(self.vakt, 'Kollaps ved scene sør', bruker=self.operator)
        lukket = services.opprett_hendelse(self.vakt, 'Fall i trapp', bruker=self.operator)
        services.skriv_linje(self.vakt, 'Pasient sendt hjem', bruker=self.operator, hendelse=lukket)
        services.lukk_hendelse(lukket, bruker=self.operator)
        side = self._hent()
        html = _del(side, 'Åpne hendelser')
        self.assertIn(f'<td class="nr">H{aapen.hendelsesnummer}</td>', html)
        self.assertIn('Kollaps ved scene sør', html)
        self.assertNotIn(f'<td class="nr">H{lukket.hendelsesnummer}</td>', html)
        self.assertIn(f'<td>{aapen.get_prioritet_display()}</td>', html, 'navnet, ikke koden')
        self.assertIn('Pasient sendt hjem', _del(side, 'Loggen'),
                      'linjene i en lukket hendelse er fortsatt loggen')


class LoggenTests(_Utskrift):

    def test_bare_de_siste_atte_timene(self):
        naa = timezone.now()
        for timer, tekst in ((LOGG_TIMER + 1, 'For gammel'), (LOGG_TIMER - 1, 'Innenfor')):
            Logglinje.objects.create(vakt=self.vakt, tidspunkt=naa - timedelta(hours=timer),
                                     tekst=tekst, forfatter_navn='ko1')
        html = self._hent()
        self.assertIn('Innenfor', html)
        self.assertNotIn('For gammel', html)

    def test_kommentaren_inne_i_hendelsen_er_med(self):
        h = services.opprett_hendelse(self.vakt, 'Kollaps', bruker=self.operator)
        services.skriv_linje(self.vakt, 'Pasient våken, sitter selv', bruker=self.operator, hendelse=h)
        html = self._hent()
        self.assertIn('Pasient våken, sitter selv', html)
        self.assertIn(f'<td class="nr">H{h.hendelsesnummer}</td>', html)

    def test_systemlinja_har_skjermens_ordlyd(self):
        h = services.opprett_hendelse(self.vakt, 'Fall i trapp', bruker=self.operator)
        services.lukk_hendelse(h, bruker=self.operator)
        html = self._hent()
        system = Logglinje.objects.filter(vakt=self.vakt, systemkode__gt='')
        self.assertTrue(system.exists())
        for linje in system:
            with self.subTest(linje.systemkode):
                self.assertIn(systemlinjer.tegn(linje.systemkode, linje.systemdata), html)

    def test_rekkefolgen_er_skrivingen_ikke_klokkeslettet(self):
        naa = timezone.now()
        services.skriv_linje(self.vakt, 'Skrevet først', bruker=self.operator,
                             tidspunkt=naa - timedelta(minutes=5), naa=naa)
        services.skriv_linje(self.vakt, 'Skrevet etterpå, skjedde før', bruker=self.operator,
                             tidspunkt=naa - timedelta(minutes=20), naa=naa)
        html = self._hent()
        self.assertLess(html.index('Skrevet først'), html.index('Skrevet etterpå, skjedde før'))

    def test_rettet_linje_staar_paa_sin_plass_med_ny_tid(self):
        naa = timezone.now()
        forste = services.skriv_linje(self.vakt, 'Bil 2 fremme', bruker=self.operator,
                                      tidspunkt=naa - timedelta(minutes=5), naa=naa)
        services.skriv_linje(self.vakt, 'Lag 3 til Village', bruker=self.operator, naa=naa)
        services.korriger(forste, bruker=self.operator, tekst='Bil 2 fremme ved Hovedscenen',
                          tidspunkt=naa - timedelta(minutes=30), naa=naa)
        html = self._hent()
        self.assertLess(html.index('Bil 2 fremme ved Hovedscenen'), html.index('Lag 3 til Village'))
        self.assertNotIn('Bil 2 fremme</td>', html, 'den overstyrte teksten er ikke med')
        self.assertIn('rettet, skrevet', html)

    def test_fjernet_linje_uten_tekst(self):
        leder = CustomUser.objects.create_user(username='leder', password='x', must_change_password=False)
        linje = services.skriv_linje(self.vakt, 'Ola Nordmann, f. 1990', bruker=self.operator)
        services.fjern(linje, bruker=leder)
        html = self._hent()
        self.assertNotIn('Ola Nordmann', html)
        self.assertIn('Innholdet er fjernet av leder', html)

    def test_brukertekst_escapes(self):
        services.skriv_linje(self.vakt, '<script>alert(1)</script>', bruker=self.operator)
        html = self.klient.get(URL).content.decode()
        self.assertNotIn('<script>alert(1)', html)
        self.assertIn('&lt;script&gt;alert(1)', html)

    def test_tidene_er_norske_og_dagen_skifter_ved_midnatt(self):
        """**Prod-formen:** ORM-en gir UTC. 21:50, 21:55 og 22:10 UTC er 23:50,
        23:55 og 00:10 i oktober i Norge — to dager. Skrevet i norsk tid ville
        testen gått grønn med en `.date()` rett på tidspunktet."""
        for t, tekst in ((datetime(2026, 10, 12, 21, 50, tzinfo=dt_tz.utc), 'Før midnatt'),
                         (datetime(2026, 10, 12, 21, 55, tzinfo=dt_tz.utc), 'Like før midnatt'),
                         (datetime(2026, 10, 12, 22, 10, tzinfo=dt_tz.utc), 'Etter midnatt')):
            Logglinje.objects.create(vakt=self.vakt, tidspunkt=t, tekst=tekst, forfatter_navn='ko1')
        with mock.patch('django.utils.timezone.now',
                        return_value=datetime(2026, 10, 12, 23, 0, tzinfo=dt_tz.utc)):
            html = self._hent()
        self.assertIn('Mandag 12. oktober 2026', html)
        self.assertIn('Tirsdag 13. oktober 2026', html)
        self.assertEqual(html.count('<tr class="dag">'), 2, 'ett dagskille per dag, ikke per linje')
        self.assertLess(html.index('Mandag 12. oktober'), html.index('Før midnatt'))
        self.assertLess(html.index('Før midnatt'), html.index('Tirsdag 13. oktober'))
        self.assertLess(html.index('Tirsdag 13. oktober'), html.index('Etter midnatt'))
        self.assertIn('<td class="tid">23:50</td>', html)
        self.assertIn('<td class="tid">00:10</td>', html)


class OppdrageneTests(_Utskrift):

    def _oppdrag(self, problemstilling):
        return Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=oservices.neste_oppdragsnummer(self.vakt),
            enhet=self.enhet, problemstilling=problemstilling, hastegrad='Akutt',
            lokasjon=self.park)

    def test_de_aktive_eldste_forst_med_enhetens_status(self):
        forste = self._oppdrag('Pustevansker')
        andre = self._oppdrag('Brystsmerter')
        oservices.sett_status(forste, choices.RYKKER_UT, enhet=self.enhet)
        html = self._hent()
        self.assertLess(html.index(f'O{forste.oppdragsnummer}'), html.index(f'O{andre.oppdragsnummer}'))
        self.assertIn('Pustevansker', html)
        self.assertIn(f'{self.enhet.navn} — {choices.status_navn_for("Akutt", choices.RYKKER_UT)}', html)

    def test_historikken_er_ikke_med(self):
        o = self._oppdrag('Ferdig for lenge siden')
        Oppdrag.objects.filter(pk=o.pk).update(historikk_fra=timezone.now())
        self.assertNotIn('Ferdig for lenge siden', _del(self._hent(), 'Aktive oppdrag'))


class TavlaTests(_Utskrift):

    def test_stedet_pausen_og_uten_plass(self):
        tavle.plasser(self.vakt, self.lag1, bruker=self.operator, lokasjon=self.park)
        tavle.plasser(self.vakt, self.lag2, bruker=self.operator, pause=True)
        html = _del(self._hent(), 'Tavla')
        self.assertIn('<td><b>Parkscene</b></td> <td>Lag 1', html)
        self.assertIn('<h3>Pause</h3> <div>Lag 2', html)
        uten_plass = html.split('<h3>Uten plass</h3>')[1].split('<h3>')[0]
        self.assertIn('<div>Ambulanse 1</div>', uten_plass)
        self.assertNotIn('Lag 1', uten_plass, 'de plasserte står ikke her')
        self.assertNotIn('Lag 2', uten_plass, 'de i pause heller ikke')
        self.assertNotIn('Lag 9', html, 'av vakt står ikke på tavla')

    def test_opptatt_har_forrang_og_bilen_krever_oppdragstilgang(self):
        tavle.plasser(self.vakt, self.bil, bruker=self.operator, lokasjon=self.club)
        o = Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=oservices.neste_oppdragsnummer(self.vakt),
            enhet=self.enhet, problemstilling='Pustevansker', hastegrad='Akutt', lokasjon=self.park)
        oservices.sett_status(o, choices.RYKKER_UT, enhet=self.enhet)
        html = _del(self._hent(), 'Tavla')
        self.assertIn(f'<h3>Opptatt</h3> <div>Ambulanse 1 — O{o.oppdragsnummer}', html)
        self.assertNotIn('<td><b>Club Venue</b></td>', html)
        ModulTilgang.objects.filter(bruker=self.operator, modul_slug='oppdrag').delete()
        html = _del(self._hent(), 'Tavla')
        self.assertNotIn('Ambulanse 1', html)
        self.assertIn('Bilene står ikke med', html)

    def test_planlagt_pause_i_vinduet_og_ikke_etter(self):
        naa = timezone.now()
        tavle.planlegg_pause(self.vakt, self.lag1, fra=naa + timedelta(hours=1),
                             til=naa + timedelta(hours=2), bruker=self.operator)
        skift(self.lag2, fra=-1, til=tavle.timer() + 4)
        etter = naa + timedelta(hours=tavle.timer() + 1)
        tavle.planlegg_pause(self.vakt, self.lag2, fra=etter, til=etter + timedelta(hours=1),
                             bruker=self.operator)
        html = _del(self._hent(), 'Tavla')
        self.assertNotIn('<td>Lag 2</td>', html, 'pausen etter vinduet står ikke')
        fra = timezone.localtime(naa + timedelta(hours=1)).strftime('%H:%M')
        self.assertIn(f'<td class="tid">{fra}–', html)
        self.assertIn('<td>Lag 1</td><td>Pause</td>', html)


class KonsertplanleggerenTests(_Utskrift):

    def test_pagaende_og_kommende_ikke_ferdige_eller_utenfor_vinduet(self):
        naa = timezone.now()
        self._lagre(navn='Pågår nå', fra=naa - timedelta(hours=1), til=naa + timedelta(hours=1))
        self._lagre(navn='Kommer snart', fra=naa + timedelta(hours=2), til=naa + timedelta(hours=3))
        self._lagre(navn='Ferdig alt', fra=naa - timedelta(hours=3), til=naa - timedelta(hours=2))
        langt = timedelta(hours=tavle.timer() + 1)
        self._lagre(navn='Langt fram', fra=naa + langt, til=naa + langt + timedelta(hours=1))
        html = self._hent()
        self.assertIn('Pågår nå', html)
        self.assertIn('Kommer snart', html)
        self.assertNotIn('Ferdig alt', html)
        self.assertNotIn('Langt fram', html)
        self.assertLess(html.index('Pågår nå'), html.index('Kommer snart'))
        self.assertEqual(html.count('Pågår</span>'), 1, 'bare den som har begynt')
        self.assertIn('Lag: 4', html)


class RessursoversiktenTests(_Utskrift):

    def setUp(self):
        super().setUp()
        skift(self.bil)
        from vaktliste.models import Mannskap
        Mannskap.objects.filter(navn__in=['Mannskap Ambulanse 1', 'Mannskap Lag 1']).update(
            telefon='99887766', issi='2041')

    def test_bilen_med_status_og_besetning_og_laget_med_mannskap(self):
        html = self._hent()
        self.assertIn('<td><b>HGSD 56</b>', html, 'bilen står med enhetsnavnet, som på kortet')
        self.assertIn('Mannskap Ambulanse 1 — 99887766 · 2041', html)
        self.assertIn('<td><b>Lag 1</b></td>', html)
        self.assertIn('Mannskap Lag 1 — 99887766 · 2041', html)
        self.assertNotIn('<td><b>Lag 9</b></td>', html, 'av vakt står ikke')

    def test_uten_vaktliste_ingen_besetning_og_ingen_lag(self):
        ModulTilgang.objects.filter(bruker=self.operator, modul_slug='vaktliste').delete()
        html = self._hent()
        self.assertNotIn('99887766', html)
        self.assertIn('Lagene står ikke med', html)
        self.assertIn('Krever lesetilgang i vaktlista', html)
        self.assertIn('<td><b>HGSD 56</b>', html, 'bilen står, uten besetning')

    def test_dataene_hentes_ikke_uten_tilgang(self):
        """Malen sjekker flaggene også, så en mutant som henter og ikke viser
        går grønn gjennom HTML-en. Det som ikke skal vises, skal heller ikke
        hentes — prøvd på funksjonen."""
        from ko.utskrift import ressurser_del
        ingen = ressurser_del(self.vakt, med_biler=False, med_vaktliste=False)
        self.assertEqual((ingen['biler'], ingen['lag']), ([], []))
        bare_biler = ressurser_del(self.vakt, med_biler=True, med_vaktliste=False)
        self.assertTrue(bare_biler['biler'])
        self.assertTrue(all(b['besetning'] is None for b in bare_biler['biler']))
        self.assertEqual(bare_biler['lag'], [])

    def test_uten_oppdrag_ingen_biler(self):
        ModulTilgang.objects.filter(bruker=self.operator, modul_slug='oppdrag').delete()
        html = self._hent()
        self.assertNotIn('<td><b>HGSD 56</b>', html)
        self.assertIn('Bilene står ikke med', html)
        self.assertIn('<td><b>Lag 1</b></td>', html)


class KopienUtenNettTests(_Utskrift):

    def test_personlig_konto_faar_hodet_og_skriptet_beskjeden(self):
        self.assertEqual(self.klient.get(URL).get(KOPI_HODE), '1')
        self.assertIn('window.KO_KOPI = true;', self.klient.get('/ko/').content.decode())

    def test_delt_konto_aldri(self):
        """KO slipper ikke inn delte kontoer (`tillat_delt_konto`), så sida er
        403 for dem allerede. Regelen prøves likevel for seg: den er laget
        under, og skal holde den dagen KO åpnes for delte kontoer."""
        from ko.utskrift import kan_lagres_lokalt
        self.assertTrue(kan_lagres_lokalt(self.operator))
        self.operator.er_delt_konto = True
        self.operator.save()
        self.assertFalse(kan_lagres_lokalt(self.operator))
        self.assertEqual(self.klient.get(URL).status_code, 403)
        self.assertFalse(kan_lagres_lokalt(type('Anonym', (), {'is_authenticated': False})()))

    def test_workeren_serveres_uten_innlogging_under_ko(self):
        svar = Client().get('/ko/sw.js')
        self.assertEqual(svar.status_code, 200)
        self.assertIn('application/javascript', svar['Content-Type'])
        self.assertEqual(svar['Service-Worker-Allowed'], '/ko/')
        self.assertEqual(svar['Cache-Control'], 'no-cache')


class WorkerReglerTests(TestCase):

    def setUp(self):
        if not node_available():
            self.skipTest('node mangler')
        from oppdrag.tests_runde_d import _konst
        self.harness = ('globalThis.self = { addEventListener: () => {} };\n'
                        + _konst(SW_JS, 'KO_SW_UTSKRIFT') + _konst(SW_JS, 'KO_SW_MAKS_ALDER_MS')
                        + build_harness([(SW_JS, ('avgjor', 'kanLagres', 'erForGammel'))]))

    def _kjor(self, snippet):
        import json
        return json.loads(run_node(self.harness, snippet).strip().splitlines()[0])

    def test_avgjor(self):
        self.assertEqual(self._kjor("""
            const o = 'https://portal.example';
            console.log(JSON.stringify([
              avgjor(o + '/ko/utskrift/', 'GET', 'cors', o),
              avgjor(o + '/ko/utskrift/', 'GET', 'navigate', o),
              avgjor(o + '/ko/', 'GET', 'navigate', o),
              avgjor(o + '/ko/', 'GET', 'cors', o),
              avgjor(o + '/ko/api/logg/', 'GET', 'cors', o),
              avgjor(o + '/ko/api/logg/ny/', 'POST', 'cors', o),
              avgjor(o + '/ko/utskrift/', 'POST', 'navigate', o),
              avgjor('https://annen.example/ko/utskrift/', 'GET', 'navigate', o),
            ]));"""), ['utskrift', 'utskrift', 'side', None, None, None, None, None])

    def test_bare_merkede_hele_svar_lagres(self):
        self.assertEqual(self._kjor("""
            const s = (ok, red, st, hode) => ({ ok, redirected: red, status: st,
              headers: { get: (n) => (n === 'X-Ko-Kopi' ? hode : null) } });
            console.log(JSON.stringify([
              kanLagres(s(true, false, 200, '1')),
              kanLagres(s(true, false, 200, null)),
              kanLagres(s(true, true, 200, '1')),
              kanLagres(s(false, false, 500, '1')),
              kanLagres(null),
            ]));"""), [True, False, False, False, False])

    def test_hoyst_et_dogn(self):
        self.assertEqual(self._kjor("""
            const n = Date.parse('2026-10-13T12:00:00Z');
            console.log(JSON.stringify([
              erForGammel('2026-10-12T12:00:01Z', n),
              erForGammel('2026-10-12T11:59:59Z', n),
              erForGammel('', n),
            ]));"""), [False, True, True])


class KopiMerketTests(_Utskrift):

    def test_merket_paa_ko_og_varselet_paa_kopien(self):
        import json
        if not node_available():
            self.skipTest('node mangler')
        ko = build_harness([(JS_DIR / 'ko.js', ('koKopiTekst',))])
        ut = run_node(ko, """
            console.log(JSON.stringify([
              koKopiTekst(new Date(2026, 9, 13, 21, 40)), koKopiTekst(null), koKopiTekst(new Date('tull'))]));""")
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), ['Klar uten nett · 21:40', '', ''])

        side = self.klient.get(URL).content.decode()
        import textwrap
        start = side.index('  function koKopiVarsel')
        skript = textwrap.dedent(side[start:side.index('(function ()', start)])
        ut = run_node(extract_function(skript, 'koKopiVarsel'), """
            const t = new Date(2026, 9, 13, 21, 40).getTime();
            console.log(JSON.stringify([
              koKopiVarsel(t, t + 60 * 1000),
              koKopiVarsel(t, t + 12 * 60 * 1000),
              koKopiVarsel(t, t + 125 * 60 * 1000),
              koKopiVarsel(NaN, t)]));""")
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), [
            '',
            'Lagret kopi fra 21:40 (12 min siden). Det som har skjedd etterpå står ikke her.',
            'Lagret kopi fra 21:40 (2 t 5 min siden). Det som har skjedd etterpå står ikke her.',
            ''])
        self.assertIn('id="kopi-varsel" hidden', side, 'skjult når sida er fersk')
