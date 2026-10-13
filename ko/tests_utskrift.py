"""KO på papir, `/ko/utskrift/` (13. okt. 2026) — `ko/utskrift.py`.

Papiret er reserven når portalen er borte midt i en vakt. Det som skal holde:

1. **Hver del viser det som gjelder nå** — de åpne hendelsene, loggen de siste
   åtte timene, de aktive oppdragene, tavla slik den står, konsertene som
   pågår og kommer.
2. **Samme fortelling som skjermen** — loggen i `gjeldende()` sin rekkefølge,
   med kommentarene i hendelsene som strømmen skjuler.
3. **Hver del har sin moduls gate** — en del man mangler tilgang til står som
   en setning, og resten skrives ut.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_tz
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from ko import services, systemlinjer, tavle
from ko.models import Logglinje
from ko.utskrift import LOGG_TIMER, valgte_deler
from oppdrag import choices
from oppdrag import services as oservices
from oppdrag.models import Oppdrag

from .tests_hendelseslogg import _gi, skift
from .tests_program import _Program

URL = '/ko/utskrift/'


def _html(svar):
    return ' '.join(svar.content.decode().split())


class DelvalgetTests(TestCase):

    def test_papirets_rekkefolge_og_ukjente_ignoreres(self):
        self.assertEqual(valgte_deler(['logg', 'tavle']), ['tavle', 'logg'])
        self.assertEqual(valgte_deler(['logg', 'tull']), ['logg'])
        alle = ['hendelser', 'oppdrag', 'tavle', 'program', 'logg']
        self.assertEqual(valgte_deler([]), alle)
        self.assertEqual(valgte_deler(['tull']), alle, 'bare ukjente er som ingen')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class _Utskrift(_Program):

    def setUp(self):
        super().setUp()
        for modul in ('ko', 'vaktliste', 'oppdrag'):
            _gi(self.operator, modul, 'les')
        _gi(self.operator, 'ko', 'skriv_full')
        self.klient = Client()
        self.klient.force_login(self.operator)

    def _hent(self, *vis):
        query = '&'.join(f'vis={v}' for v in vis)
        svar = self.klient.get(f'{URL}?{query}' if query else URL)
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
        self.assertIn('Ingen åpne hendelser.', html, 'KOs egne deler står')

    def test_med_tilgang_ingen_setning(self):
        html = self._hent()
        self.assertNotIn('krever lesetilgang', html)

    def test_vis_velger_delene(self):
        html = self._hent('tavle')
        self.assertIn('<h2>Tavla</h2>', html)
        self.assertNotIn('<h2>Loggen', html)
        self.assertNotIn('<h2>Aktive oppdrag</h2>', html)

    def test_ikonet_i_hvert_vindu(self):
        html = _html(self.klient.get('/ko/'))
        for vis in ('hendelser', 'logg', 'oppdrag', 'tavle', 'program'):
            with self.subTest(vis):
                self.assertIn(f'href="{URL}?vis={vis}"', html)


class HendelseneTests(_Utskrift):

    def test_bare_de_aapne_men_loggen_har_den_lukkede(self):
        aapen = services.opprett_hendelse(self.vakt, 'Kollaps ved scene sør', bruker=self.operator)
        lukket = services.opprett_hendelse(self.vakt, 'Fall i trapp', bruker=self.operator)
        services.skriv_linje(self.vakt, 'Pasient sendt hjem', bruker=self.operator, hendelse=lukket)
        services.lukk_hendelse(lukket, bruker=self.operator)
        html = self._hent('hendelser')
        self.assertIn(f'<td class="nr">H{aapen.hendelsesnummer}</td>', html)
        self.assertIn('Kollaps ved scene sør', html)
        self.assertNotIn(f'<td class="nr">H{lukket.hendelsesnummer}</td>', html)
        self.assertIn(f'<td>{aapen.get_prioritet_display()}</td>', html, 'navnet, ikke koden')
        self.assertIn('Pasient sendt hjem', self._hent('logg'),
                      'linjene i en lukket hendelse er fortsatt loggen')


class LoggenTests(_Utskrift):

    def test_bare_de_siste_atte_timene(self):
        naa = timezone.now()
        for timer, tekst in ((LOGG_TIMER + 1, 'For gammel'), (LOGG_TIMER - 1, 'Innenfor')):
            Logglinje.objects.create(vakt=self.vakt, tidspunkt=naa - timedelta(hours=timer),
                                     tekst=tekst, forfatter_navn='ko1')
        html = self._hent('logg')
        self.assertIn('Innenfor', html)
        self.assertNotIn('For gammel', html)

    def test_kommentaren_inne_i_hendelsen_er_med(self):
        h = services.opprett_hendelse(self.vakt, 'Kollaps', bruker=self.operator)
        services.skriv_linje(self.vakt, 'Pasient våken, sitter selv', bruker=self.operator, hendelse=h)
        html = self._hent('logg')
        self.assertIn('Pasient våken, sitter selv', html)
        self.assertIn(f'<td class="nr">H{h.hendelsesnummer}</td>', html)

    def test_systemlinja_har_skjermens_ordlyd(self):
        h = services.opprett_hendelse(self.vakt, 'Fall i trapp', bruker=self.operator)
        services.lukk_hendelse(h, bruker=self.operator)
        html = self._hent('logg')
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
        html = self._hent('logg')
        self.assertLess(html.index('Skrevet først'), html.index('Skrevet etterpå, skjedde før'))

    def test_rettet_linje_staar_paa_sin_plass_med_ny_tid(self):
        naa = timezone.now()
        forste = services.skriv_linje(self.vakt, 'Bil 2 fremme', bruker=self.operator,
                                      tidspunkt=naa - timedelta(minutes=5), naa=naa)
        services.skriv_linje(self.vakt, 'Lag 3 til Village', bruker=self.operator, naa=naa)
        services.korriger(forste, bruker=self.operator, tekst='Bil 2 fremme ved Hovedscenen',
                          tidspunkt=naa - timedelta(minutes=30), naa=naa)
        html = self._hent('logg')
        self.assertLess(html.index('Bil 2 fremme ved Hovedscenen'), html.index('Lag 3 til Village'))
        self.assertNotIn('Bil 2 fremme</td>', html, 'den overstyrte teksten er ikke med')
        self.assertIn('rettet, skrevet', html)

    def test_fjernet_linje_uten_tekst(self):
        leder = CustomUser.objects.create_user(username='leder', password='x', must_change_password=False)
        linje = services.skriv_linje(self.vakt, 'Ola Nordmann, f. 1990', bruker=self.operator)
        services.fjern(linje, bruker=leder)
        html = self._hent('logg')
        self.assertNotIn('Ola Nordmann', html)
        self.assertIn('Innholdet er fjernet av leder', html)

    def test_brukertekst_escapes(self):
        services.skriv_linje(self.vakt, '<script>alert(1)</script>', bruker=self.operator)
        html = self.klient.get(f'{URL}?vis=logg').content.decode()
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
            html = self._hent('logg')
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
        html = self._hent('oppdrag')
        self.assertLess(html.index(f'O{forste.oppdragsnummer}'), html.index(f'O{andre.oppdragsnummer}'))
        self.assertIn('Pustevansker', html)
        self.assertIn(f'{self.enhet.navn} — {choices.status_navn_for("Akutt", choices.RYKKER_UT)}', html)

    def test_historikken_er_ikke_med(self):
        o = self._oppdrag('Ferdig for lenge siden')
        Oppdrag.objects.filter(pk=o.pk).update(historikk_fra=timezone.now())
        self.assertNotIn('Ferdig for lenge siden', self._hent('oppdrag'))


class TavlaTests(_Utskrift):

    def test_stedet_pausen_og_uten_plass(self):
        tavle.plasser(self.vakt, self.lag1, bruker=self.operator, lokasjon=self.park)
        tavle.plasser(self.vakt, self.lag2, bruker=self.operator, pause=True)
        html = self._hent('tavle')
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
        html = self._hent('tavle')
        self.assertIn(f'<h3>Opptatt</h3> <div>Ambulanse 1 — O{o.oppdragsnummer}', html)
        self.assertNotIn('<td><b>Club Venue</b></td>', html)
        ModulTilgang.objects.filter(bruker=self.operator, modul_slug='oppdrag').delete()
        html = self._hent('tavle')
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
        html = self._hent('tavle')
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
        html = self._hent('program')
        self.assertIn('Pågår nå', html)
        self.assertIn('Kommer snart', html)
        self.assertNotIn('Ferdig alt', html)
        self.assertNotIn('Langt fram', html)
        self.assertLess(html.index('Pågår nå'), html.index('Kommer snart'))
        self.assertEqual(html.count('Pågår</span>'), 1, 'bare den som har begynt')
        self.assertIn('Lag: 4', html)
