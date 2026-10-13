"""Utskriften av KO-loggen, `/ko/utskrift/` (13. okt. 2026).

Tre ting skal holde, og alle tre er grunnen til at den finnes:

1. **Alt står der** — også kommentarene inne i hendelsene, som loggstrømmen
   skjuler. Utskriften er stedet der ingenting «bare ble sagt inne i hendelsen».
2. **Samme fortelling som skjermen** — `gjeldende()` sin rekkefølge, rettede
   linjer på sin opprinnelige plass, fjernede uten tekst.
3. **`les` betyr denne vakta** — en tidligere vakts logg krever `skriv_leder`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_tz

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.models import Vakt
from core.vakt import hent_aktiv_vakt
from ko import services, systemlinjer
from ko.models import Logglinje

URL = '/ko/utskrift/'


def _bruker(navn, nivaa=None):
    bruker = CustomUser.objects.create_user(username=navn, password='x', must_change_password=False)
    if nivaa:
        ModulTilgang.objects.create(bruker=bruker, modul_slug='ko', nivaa=nivaa)
    return bruker


def _klient(bruker):
    klient = Client()
    klient.force_login(bruker)
    return klient


def _html(svar):
    return ' '.join(svar.content.decode().split())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(TestCase):

    def test_anonym_sendes_til_innlogging(self):
        svar = Client().get(URL)
        self.assertEqual(svar.status_code, 302)
        self.assertIn('/accounts/login/', svar['Location'])

    def test_uten_ko_rad_stengt(self):
        self.assertEqual(_klient(_bruker('uten')).get(URL).status_code, 403)

    def test_les_faar_aktiv_vakt(self):
        svar = _klient(_bruker('leser', 'les')).get(URL)
        self.assertEqual(svar.status_code, 200)
        self.assertContains(svar, hent_aktiv_vakt().navn)

    def test_tar_ikke_imot_skriving(self):
        self.assertEqual(_klient(_bruker('leser', 'les')).post(URL).status_code, 405)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AltStaarDerTests(TestCase):

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.kari = _bruker('kari', 'skriv_full')
        self.klient = _klient(self.kari)

    def test_kommentaren_inne_i_hendelsen_er_med(self):
        h = services.opprett_hendelse(self.vakt, 'Kollaps ved scene sør', bruker=self.kari)
        services.skriv_linje(self.vakt, 'Pasient våken, sitter selv', bruker=self.kari, hendelse=h)
        html = _html(self.klient.get(URL))
        self.assertIn('Pasient våken, sitter selv', html)
        self.assertIn(f'<td class="h">H{h.hendelsesnummer}</td>', html)
        self.assertIn('Kollaps ved scene sør', html, 'hendelsen står i oversikten')
        self.assertIn(f'<td>{h.get_prioritet_display()}</td>', html, 'navnet, ikke koden')

    def test_systemlinja_har_skjermens_ordlyd(self):
        h = services.opprett_hendelse(self.vakt, 'Fall i trapp', bruker=self.kari)
        services.lukk_hendelse(h, bruker=self.kari)
        html = _html(self.klient.get(URL))
        system = Logglinje.objects.filter(vakt=self.vakt, systemkode__gt='')
        self.assertTrue(system.exists())
        for linje in system:
            with self.subTest(linje.systemkode):
                self.assertIn(systemlinjer.tegn(linje.systemkode, linje.systemdata), html)

    def test_rettet_linje_staar_paa_sin_plass_med_ny_tid(self):
        naa = timezone.now()
        forste = services.skriv_linje(self.vakt, 'Bil 2 fremme', bruker=self.kari,
                                      tidspunkt=naa - timedelta(minutes=5), naa=naa)
        services.skriv_linje(self.vakt, 'Lag 3 til Village', bruker=self.kari, naa=naa)
        services.korriger(forste, bruker=self.kari, tekst='Bil 2 fremme ved Hovedscenen',
                          tidspunkt=naa - timedelta(minutes=30), naa=naa)
        html = _html(self.klient.get(URL))
        rettet = html.index('Bil 2 fremme ved Hovedscenen')
        self.assertLess(rettet, html.index('Lag 3 til Village'),
                        'rettingen står der linja ble skrevet, ikke etter rettet tid')
        self.assertNotIn('Bil 2 fremme</td>', html, 'den overstyrte teksten er ikke med')
        self.assertIn('rettet, skrevet', html)
        self.assertIn(timezone.localtime(naa - timedelta(minutes=30)).strftime('%H:%M'), html)

    def test_rekkefolgen_er_skrivingen_ikke_klokkeslettet(self):
        """§4.3: «Kl. 21:14» skrevet klokka 21:40 står etter det som ble skrevet
        21:30 — loggen er en fortelling, og den hopper ikke rundt."""
        naa = timezone.now()
        services.skriv_linje(self.vakt, 'Skrevet først', bruker=self.kari,
                             tidspunkt=naa - timedelta(minutes=5), naa=naa)
        services.skriv_linje(self.vakt, 'Skrevet etterpå, skjedde før', bruker=self.kari,
                             tidspunkt=naa - timedelta(minutes=20), naa=naa)
        html = _html(self.klient.get(URL))
        self.assertLess(html.index('Skrevet først'), html.index('Skrevet etterpå, skjedde før'))

    def test_fjernet_linje_uten_tekst(self):
        leder = _bruker('leder', 'skriv_leder')
        linje = services.skriv_linje(self.vakt, 'Ola Nordmann, f. 1990', bruker=self.kari)
        services.fjern(linje, bruker=leder)
        html = _html(self.klient.get(URL))
        self.assertNotIn('Ola Nordmann', html)
        self.assertIn('Innholdet er fjernet av leder', html)

    def test_brukertekst_escapes(self):
        services.skriv_linje(self.vakt, '<script>alert(1)</script>', bruker=self.kari)
        html = self.klient.get(URL).content.decode()
        self.assertNotIn('<script>alert(1)', html)
        self.assertIn('&lt;script&gt;alert(1)', html)

    def test_tidene_er_norske_og_dagen_skifter_ved_midnatt(self):
        """**Prod-formen:** ORM-en gir UTC. 21:50 og 22:10 UTC er 23:50 og 00:10
        i oktober i Norge — og hver sin dag. Skrevet i norsk tid ville testen
        gått grønn med en `.date()` rett på tidspunktet."""
        for t, tekst in ((datetime(2026, 10, 12, 21, 50, tzinfo=dt_tz.utc), 'Før midnatt'),
                         (datetime(2026, 10, 12, 21, 55, tzinfo=dt_tz.utc), 'Like før midnatt'),
                         (datetime(2026, 10, 12, 22, 10, tzinfo=dt_tz.utc), 'Etter midnatt')):
            Logglinje.objects.create(vakt=self.vakt, tidspunkt=t, tekst=tekst,
                                     forfatter=self.kari, forfatter_navn='kari')
        html = _html(self.klient.get(URL))
        self.assertIn('Mandag 12. oktober 2026', html)
        self.assertIn('Tirsdag 13. oktober 2026', html)
        self.assertLess(html.index('Mandag 12. oktober'), html.index('Før midnatt'))
        self.assertLess(html.index('Før midnatt'), html.index('Tirsdag 13. oktober'))
        self.assertLess(html.index('Tirsdag 13. oktober'), html.index('Etter midnatt'))
        self.assertEqual(html.count('<tr class="dag">'), 2, 'ett dagskille per dag, ikke per linje')
        self.assertIn('<td class="tid">23:50</td>', html)
        self.assertIn('<td class="tid">00:10</td>', html)

    def test_lenken_fra_ko(self):
        self.assertContains(self.klient.get('/ko/'), f'href="{URL}"')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TidligereVaktTests(TestCase):

    def setUp(self):
        self.aktiv = hent_aktiv_vakt()
        start = timezone.now() - timedelta(days=400)
        self.gammel = Vakt.objects.create(navn='Fjorårets stevne', year=start.year, startet=start,
                                          avsluttet=start + timedelta(days=2), er_aktiv=False)
        Logglinje.objects.create(vakt=self.gammel, tidspunkt=start, tekst='Gammel linje',
                                 forfatter_navn='per')

    def test_les_faar_ikke_tidligere_vakt(self):
        klient = _klient(_bruker('leser', 'les'))
        self.assertEqual(klient.get(f'{URL}?vakt={self.gammel.pk}').status_code, 403)
        self.assertEqual(klient.get(f'{URL}?vakt={self.aktiv.pk}').status_code, 200)
        self.assertNotContains(klient.get(URL), 'Fjorårets stevne', msg_prefix='ingen vaktvelger')

    def test_skriv_leder_faar_den(self):
        klient = _klient(_bruker('leder', 'skriv_leder'))
        svar = klient.get(f'{URL}?vakt={self.gammel.pk}')
        self.assertEqual(svar.status_code, 200)
        html = _html(svar)
        self.assertIn('Gammel linje', html)
        self.assertIn('tidligere vakt', html)
        self.assertIn(f'<option value="{self.gammel.pk}" selected>Fjorårets stevne</option>', html)
        self.assertNotIn('Gammel linje', _html(klient.get(URL)), 'standard er aktiv vakt')

    def test_ukjent_eller_ugyldig_vakt(self):
        klient = _klient(_bruker('leder', 'skriv_leder'))
        self.assertEqual(klient.get(f'{URL}?vakt=99999').status_code, 404)
        self.assertEqual(klient.get(f'{URL}?vakt=abc').status_code, 404)
