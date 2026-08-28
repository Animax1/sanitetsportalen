"""Hvert endepunkt under en modul må være dekorert med ``@modul_kreves``.

Dette er vernet §6 i ``docs/BESLUTNING_ROLLEMODELLEN.md`` etterlyser. Risikoen
ved å bruke dekoratør framfor middleware er en glemt dekoratør på et nytt
endepunkt — og gjennomgangen som ble gjort for hånd (CHANGELOG 22. aug.,
«Kontrollert og funnet i orden») holder bare til neste endepunkt noen skriver.

Testen går gjennom ``urlpatterns`` for modulens prefiks og krever at hvert
view bærer markøren dekoratøren setter. Den gjetter ikke: `modul_kreves`
setter ``_modul_kreves`` eksplisitt, og en gjetning som tar feil den ene veien
ville sluppet et udekorert endepunkt gjennom.
"""
import json

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import get_resolver


# Ruter som med vilje står uten modulkrav, med begrunnelse. Lista er kort og
# skal bli det: hvert innslag er et endepunkt som er nåbart uten modultilgang.
UNNTAK = {
    'api_full_stats_flyttet':
        'ren videresending til /statistikk/, som har sin egen gate',
    'api_arkiv_full_stats_flyttet':
        'ren videresending til /statistikk/, som har sin egen gate',
    'legacy_server_status_redirect':
        'ren videresending til /portal-admin/server-status/, som er admin-gatet',
}


def _ruter_under(prefiks):
    """[(navn, callback, mønster)] for alle ruter under et URL-prefiks."""
    ut = []

    def gaa(resolver, sti=''):
        for m in resolver.url_patterns:
            nytt = sti + str(getattr(m, 'pattern', ''))
            if hasattr(m, 'url_patterns'):
                gaa(m, nytt)
            else:
                if nytt.startswith(prefiks):
                    ut.append((m.name, m.callback, nytt))

    gaa(get_resolver())
    return ut


class ModulDekoratorTests(SimpleTestCase):
    """Alle patients- og statistikk-ruter er dekorert."""

    def _udekorerte(self, prefiks, forventet_slug):
        funn = []
        for navn, callback, monster in _ruter_under(prefiks):
            if navn in UNNTAK:
                continue
            krav = getattr(callback, '_modul_kreves', None)
            if krav is None:
                funn.append(f'{monster} ({navn or "uten navn"})')
            elif krav[0] != forventet_slug:
                funn.append(
                    f'{monster} krever modul «{krav[0]}», forventet '
                    f'«{forventet_slug}»')
        return funn

    def test_alle_pasientruter_er_dekorert(self):
        funn = self._udekorerte('pasienter/', 'patients')
        self.assertEqual(funn, [], (
            'Endepunkter under /pasienter/ uten @modul_kreves:\n  '
            + '\n  '.join(funn)
            + '\n\nEt udekorert endepunkt er naabart for enhver innlogget '
              'bruker — det var nettopp hullet i §2.1. Legg paa dekoratoeren, '
              'eller foer ruta opp i UNNTAK med en begrunnelse.'
        ))

    def test_alle_statistikkruter_er_dekorert(self):
        funn = self._udekorerte('statistikk/', 'statistikk')
        self.assertEqual(funn, [], (
            'Endepunkter under /statistikk/ uten @modul_kreves:\n  '
            + '\n  '.join(funn)
        ))

    def test_testen_finner_faktisk_ruter(self):
        """Vern mot at testen blir tom og dermed alltid grønn.

        En URL-gjennomgang som ikke finner noen ruter passerer trivielt. Det
        har skjedd i denne kodebasen før, med en annen test samme dag.
        """
        self.assertGreaterEqual(len(_ruter_under('pasienter/')), 10)
        self.assertGreaterEqual(len(_ruter_under('statistikk/')), 3)

    def test_unntakene_finnes_fortsatt(self):
        """En begrunnelse for en rute som er borte er bare støy."""
        navn = {n for n, _, _ in _ruter_under('pasienter/')}
        navn |= {n for n, _, _ in _ruter_under('statistikk/')}
        forsvunnet = set(UNNTAK) - navn
        self.assertEqual(forsvunnet, set(),
                         f'UNNTAK viser til ruter som ikke finnes: {forsvunnet}')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class HulletFraParagraf21Tests(TestCase):
    """Akseptansekriteriet: hullet §2.1 dokumenterte er lukket.

    Notatet målte dette ved å kjøre koden, ikke ved å lese den. En
    En bruker med skriverolle, men uten modultilgang, fikk:

        GET  /pasienter/                 -> 200
        GET  /pasienter/api/patients/    -> 200
        POST /pasienter/api/patients/    -> 201   (pasient opprettet)

    Alle tre skal nå gi 403. Testen er skrevet med de samme tre kallene, i
    samme rekkefølge, slik at den kan leses opp mot notatet.
    """

    def setUp(self):
        from accounts.models import CustomUser
        # Bevisst UTEN gi_standardtilgang: fraværet av rader er hele poenget.
        self.uten = CustomUser.objects.create_user(
            username='hull', password='x', role='bruker',
            must_change_password=False,
        )
        self.client = Client()
        self.client.force_login(self.uten)

    def test_siden_gir_403(self):
        self.assertEqual(self.client.get('/pasienter/').status_code, 403)

    def test_lesing_av_pasienter_gir_403(self):
        self.assertEqual(
            self.client.get('/pasienter/api/patients/').status_code, 403)

    def test_oppretting_av_pasient_gir_403_og_lager_ingenting(self):
        from patients.models import Patient
        resp = self.client.post(
            '/pasienter/api/patients/',
            data=json.dumps({'grovsortering': 'Grønn'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Patient.objects.count(), 0,
                         'et avvist kall skal ikke ha opprettet noe')

    def test_registrene_gir_403(self):
        for sti in ('/pasienter/api/forstehjelpere/',
                    '/pasienter/api/helsepersonell/'):
            with self.subTest(sti=sti):
                self.assertEqual(self.client.get(sti).status_code, 403)

    def test_med_tilgang_slipper_inn_igjen(self):
        """Vern mot at testen over passerer fordi alt er stengt for alle."""
        from accounts.test_helpers import gi_standardtilgang
        gi_standardtilgang(self.uten, 'skriver')
        self.assertEqual(self.client.get('/pasienter/').status_code, 200)
        self.assertEqual(
            self.client.get('/pasienter/api/patients/').status_code, 200)
