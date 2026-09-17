"""KO-modulen, pulje 1: at skallet og tilgangen faktisk virker.

«Tilgangen må virke før noe legges bak den» (§10) er hele begrunnelsen for at
denne puljen er først. Da er det tilgangen som må prøves, ikke at siden
rendrer.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.sessions.backends.db import SessionStore
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.models import ModuleSettings
from core.modules import get_module
from ko.tilstede import tilstede


def _bruker(navn, **kwargs):
    return CustomUser.objects.create_user(
        username=navn, password='x', must_change_password=False, **kwargs)


def _gi_ko(bruker, nivaa='les'):
    return ModulTilgang.objects.update_or_create(
        bruker=bruker, modul_slug='ko', defaults={'nivaa': nivaa})


class ModuldeklarasjonenTests(SimpleTestCase):

    def test_modulen_er_registrert(self):
        modul = get_module('ko')
        self.assertIsNotNone(modul, 'ko står ikke i core/modules.py')
        self.assertEqual(modul.url, '/ko/')

    def test_nivaaene_er_dem_puljene_har_gitt_mening(self):
        """**Et nivå som ikke gir noe er lett å dele ut i god tro.**

        Pulje 1 deklarerte bare `les`, fordi skallet ikke hadde et eneste
        skriveendepunkt: et `skriv_full` delt ut da ville ligget i basen og
        **trådt stille i kraft** den dagen loggen landet, uten at noen tok den
        avgjørelsen da. Pulje 2 la til `skriv_full` (fører loggen) og
        `skriv_leder` (sletteinngangen og tidligere vakter) i samme commit som
        endepunktene som gir dem mening.

        Feiler denne fordi en pulje har lagt til sitt nivå, skal lista her
        oppdateres — i den commiten, ikke etterpå.
        """
        self.assertEqual(get_module('ko').nivaaer,
                         ('les', 'skriv_full', 'skriv_leder'))

    def test_skriv_handling_er_ikke_deklarert(self):
        """Det finnes ingen navngitt overgang i KO — og da skal nivået ikke
        tilbys. `skriv_handling` leser ikke request-kroppen; å føre en
        logglinje gjør nettopp det. Nivået ville sett ut som «får skrive
        litt», og vært en tilgang uten et endepunkt bak seg."""
        self.assertNotIn('skriv_handling', get_module('ko').nivaaer)

    def test_hvert_deklarert_nivaa_har_en_etikett(self):
        """`skriv_handling` betyr «stempling» i oppdrag og «fører sitt eget
        korps» i vaktlista. Uten en etikett per modul deles nivået ut med feil
        modul i hodet — se §4.5 i vaktlistenotatet."""
        modul = get_module('ko')
        merket = {verdi for verdi, _ in modul.nivaa_navn}
        self.assertEqual(set(modul.nivaaer) - merket, set())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TilgangenVirkerTests(TestCase):
    """Akseptansekriteriet for pulje 1, målt ved å kjøre koden.

    Rekkefølgen er den samme som `HulletFraParagraf21Tests` bruker for
    pasientmodulen, slik at de to kan leses opp mot hverandre.
    """

    def setUp(self):
        self.client = Client()

    def test_anonym_sendes_til_innlogging(self):
        for sti in ('/ko/', '/ko/api/tilstede/'):
            with self.subTest(sti=sti):
                svar = self.client.get(sti)
                self.assertIn(svar.status_code, (302, 403))

    def test_innlogget_uten_rad_gir_403(self):
        """**Fravær av rad er ingen tilgang.** Det finnes ingen `'ingen'`-verdi
        å lagre, så en konto uten rad skal møte døra — også på siden, ikke bare
        på endepunktet."""
        self.client.force_login(_bruker('uten'))
        self.assertEqual(self.client.get('/ko/').status_code, 403)
        self.assertEqual(self.client.get('/ko/api/tilstede/').status_code, 403)

    def test_rad_paa_en_annen_modul_gir_ikke_ko(self):
        """Vern mot at testen over passerer fordi alt er stengt for alle på
        feil grunnlag: tilgang til *en* modul er ikke tilgang til KO."""
        bruker = _bruker('annen')
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='patients', nivaa='skriv_full')
        self.client.force_login(bruker)
        self.assertEqual(self.client.get('/ko/').status_code, 403)

    def test_les_slipper_inn(self):
        bruker = _bruker('leser')
        _gi_ko(bruker)
        self.client.force_login(bruker)
        self.assertEqual(self.client.get('/ko/').status_code, 200)
        svar = self.client.get('/ko/api/tilstede/')
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(json.loads(svar.content)['status'], 'ok')

    def test_global_admin_slipper_inn_uten_rad(self):
        """Global admin står utenfor modulaksen og trenger ingen rader."""
        self.client.force_login(_bruker('sjef', role='admin'))
        self.assertEqual(self.client.get('/ko/').status_code, 200)

    def test_deaktivert_modul_stenger_for_andre_enn_admin(self):
        """`ModuleSettings.enabled=False` gir 403 for alle andre enn global
        admin — ellers kunne man deaktivere seg selv ut av å reaktivere."""
        bruker = _bruker('leser2')
        _gi_ko(bruker)
        ModuleSettings.objects.update_or_create(
            slug='ko', defaults={'enabled': False})
        self.client.force_login(bruker)
        self.assertEqual(self.client.get('/ko/').status_code, 403)

        self.client.force_login(_bruker('sjef2', role='admin'))
        self.assertEqual(self.client.get('/ko/').status_code, 200)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SidebarenTests(TestCase):
    """§5.3 — og de tre valgene notatets ene setning ikke tar."""

    def setUp(self):
        self.client = Client()

    def _logg_inn_som(self, bruker):
        """Egen klient per bruker, slik at hver innlogging blir en egen
        sesjonsrad. Samme klient ville byttet ut sesjonen i stedet."""
        klient = Client()
        klient.force_login(bruker)
        return klient

    def test_global_admin_er_med_selv_uten_rad(self):
        """**Notatets filter var feil, og feilen var stille.**

        «`_list_active_sessions` filtrert på `ModulTilgang('ko')`» ville
        utelatt global admin, som ingen rader har og full tilgang — altså
        nettopp den som sitter i KO og administrerer portalen. Hun ville sett
        alle andre og ikke seg selv, og lista hadde sett riktig ut.
        """
        sjef = _bruker('sjef', role='admin')
        self._logg_inn_som(sjef)
        navn = [r['brukernavn'] for r in tilstede()]
        self.assertIn('sjef', navn)

    def test_konto_uten_ko_tilgang_er_ikke_med(self):
        self._logg_inn_som(_bruker('utenfor'))
        self.assertEqual([r['brukernavn'] for r in tilstede()], [])

    def test_konto_med_rad_er_med(self):
        bruker = _bruker('operator')
        _gi_ko(bruker)
        self._logg_inn_som(bruker)
        self.assertEqual([r['brukernavn'] for r in tilstede()], ['operator'])

    def test_rad_paa_en_annen_modul_gir_ikke_plass_i_lista(self):
        """**Filteret må bære slugen, ikke bare brukeren.**

        Funnet ved mutasjonstesting: fjernes `modul_slug=SLUG` fra spørringen i
        `_har_ko_tilgang_ider`, overlever mutanten — for testen over prøver en
        konto uten *noen* rader, og den faller ut uansett. Feilen den slipper
        gjennom er den dyre: hvem som helst med tilgang til én modul ville stått
        oppført som til stede i KO.
        """
        bruker = _bruker('pasientfolk')
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='patients', nivaa='skriv_full')
        self._logg_inn_som(bruker)
        self.assertEqual([r['brukernavn'] for r in tilstede()], [])

    def test_den_ferskeste_fanen_vinner(self):
        """Står PC-en urørt i to timer mens telefonen brukes, er personen til
        stede. Mutanten `min` → `max` gir det motsatte svaret, og lista ville
        meldt fravær om noen som satt der."""
        from django.contrib.sessions.models import Session
        from core.middleware import SISTE_INTERAKSJON

        bruker = _bruker('operator')
        _gi_ko(bruker)
        self._logg_inn_som(bruker)
        self._logg_inn_som(bruker)

        naa = timezone.now()
        for sesjon, alder in zip(Session.objects.all(), (2 * 3600, 30)):
            data = sesjon.get_decoded()
            data[SISTE_INTERAKSJON] = (naa - timedelta(seconds=alder)).isoformat()
            Session.objects.filter(pk=sesjon.pk).update(
                session_data=SessionStore().encode(data))

        self.assertLess(tilstede()[0]['inaktiv_s'], 120)

    def test_en_kjent_verdi_slaar_ukjent(self):
        """`None` er «vet ikke», ikke «lenge siden». Har én fane meldt inn
        aktivitet, vet vi noe om personen — og det er det svaret lista skal gi.
        Mutanten som lar `None` vinne ville gjort hver operatør med én gammel
        fane til «ukjent»."""
        from django.contrib.sessions.models import Session
        from core.middleware import SISTE_INTERAKSJON

        bruker = _bruker('operator')
        _gi_ko(bruker)
        self._logg_inn_som(bruker)   # uten aktivitet: inaktiv_s = None
        klient = self._logg_inn_som(bruker)
        klient.get('/ko/api/tilstede/', HTTP_X_PORTAL_INAKTIV='5')

        self.assertIsNotNone(tilstede()[0]['inaktiv_s'])

    def test_deaktivert_modul_tar_alle_andre_enn_admin_ut_av_lista(self):
        bruker = _bruker('operator')
        _gi_ko(bruker)
        sjef = _bruker('sjef', role='admin')
        self._logg_inn_som(bruker)
        self._logg_inn_som(sjef)
        ModuleSettings.objects.update_or_create(
            slug='ko', defaults={'enabled': False})
        self.assertEqual([r['brukernavn'] for r in tilstede()], ['sjef'])

    def test_en_rad_per_person_ikke_per_sesjon(self):
        """Adminlista lister sesjoner, fordi den skal kunne avslutte én av
        dem. Denne svarer på hvem som er der — og samme operatør med KO på
        PC-en og på telefonen er én person."""
        bruker = _bruker('operator')
        _gi_ko(bruker)
        self._logg_inn_som(bruker)
        self._logg_inn_som(bruker)
        self.assertEqual([r['brukernavn'] for r in tilstede()], ['operator'])

    def test_delt_konto_er_merket(self):
        """**En delt konto må se ut som en delt konto** (§4.5). «Enhet 2» er
        to til tre personer; «Kari Nordmann» er én."""
        bruker = _bruker('enhet-2', er_delt_konto=True)
        _gi_ko(bruker)
        self._logg_inn_som(bruker)
        self.assertTrue(tilstede()[0]['er_delt_konto'])

    def test_sesjonsnokkelen_slipper_aldri_ut(self):
        """`session_key` er adminflatens håndtak for å **avslutte** en sesjon.
        Et felt hvis eneste bruk er destruktiv skal ikke ligge i et svar en
        hvilken som helst operatør henter hvert 30. sekund."""
        bruker = _bruker('operator')
        _gi_ko(bruker)
        klient = self._logg_inn_som(bruker)
        svar = klient.get('/ko/api/tilstede/')
        self.assertEqual(svar.status_code, 200)
        kropp = svar.content.decode()
        self.assertNotIn('session_key', kropp)
        for rad in json.loads(kropp)['data']:
            self.assertEqual(set(rad), {
                'brukernavn', 'er_delt_konto', 'er_global_admin', 'inaktiv_s'})

    def test_utlopt_sesjon_teller_ikke(self):
        """Sperrehake mot at lista bare er «alle kontoer med KO-tilgang»."""
        from django.contrib.sessions.models import Session

        bruker = _bruker('operator')
        _gi_ko(bruker)
        self._logg_inn_som(bruker)
        Session.objects.update(expire_date=timezone.now() - timedelta(days=1))
        self.assertEqual(tilstede(), [])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SidenHarIngenFanerTests(TestCase):
    """Flatene skal stå ved siden av hverandre, ikke bak hverandre.

    **Regelen har ingen kjøretid** — den bor i markupen — så den prøves ved å
    rendre det ekte viewet og se på svaret, ikke ved å lese malfila. Da fanges
    også en fane som kommer inn via et inkludert partial.

    Pulje 1 la de fire flatene i `nav-tabs`. Det er feil form her: tre av fire
    trengs for å fullføre **én** handling (hør, før linja, se hvem som er
    ledig, send), og en skjult fane er dessuten en fane man ikke vet har endret
    seg — siden poller, så andres logglinjer og nye oppdrag lander i en rute
    ingen ser på. Se `ko/CLAUDE.md`.
    """

    def setUp(self):
        self.client = Client()
        bruker = _bruker('operator')
        _gi_ko(bruker, 'skriv_full')
        self.client.force_login(bruker)

    def _markup(self) -> str:
        svar = self.client.get('/ko/')
        self.assertEqual(svar.status_code, 200)
        return svar.content.decode()

    def test_ingen_fanemekanikk_i_markupen(self):
        markup = self._markup()
        for spor in ('nav-tabs', 'data-bs-toggle="tab"', 'tab-pane',
                     'role="tablist"'):
            with self.subTest(spor=spor):
                self.assertNotIn(
                    spor, markup,
                    f'{spor} er tilbake på /ko/ — flatene skal stå ved siden '
                    f'av hverandre. En ny flate legges i en av kolonnene, '
                    f'aldri som en fane til')

    def test_loggen_og_tavla_staar_samtidig(self):
        """Det er *dette* fraværet av faner skal gi, og derfor det som prøves.

        En test som bare nektet `nav-tabs` ville gått grønn om noen skjulte
        flatene med en annen mekanisme — et `d-none` og en egen knapp gjør
        samme skade uten å hete det samme.
        """
        markup = self._markup()
        self.assertIn('id="ko-logg-form"', markup, 'skrivefeltet mangler')
        self.assertIn('id="ko-logg-liste"', markup, 'loggstrømmen mangler')
        self.assertIn('Ressursoversikt', markup, 'tavla mangler')
        self.assertIn('Oppdrag og hendelser', markup, 'oppdragsflata mangler')
        self.assertNotIn('d-none', markup.split('id="ko-logg-form"')[0][-400:],
                         'noe skjuler loggen ved lasting')
