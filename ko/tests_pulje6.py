"""Pulje 6: chat, ansvarsmerket og det som gates rundt dem.

Chat er et **merke på linja i samme logg** (§4.5), ikke en tabell — og
admin-bryteren avgjør om operatørene får sette merket, ikke om linjene som alt
finnes vises. Ansvarsmerket (§5.1) **vises og styrer ingenting** (André,
18. sep. 2026). Begge deler prøves der reglene bor: tjenestelaget tungt,
portene som porter.
"""
from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from core.models import AppSetting
from core.vakt import hent_aktiv_vakt
from ko import services
from ko.models import Ansvarsmerke, Logglinje
from ko.tilstede import tilstede


def _bruker(navn, **kwargs):
    return CustomUser.objects.create_user(
        username=navn, password='x', must_change_password=False, **kwargs)


def _gi(bruker, modul, nivaa):
    ModulTilgang.objects.update_or_create(
        bruker=bruker, modul_slug=modul, defaults={'nivaa': nivaa})
    return bruker


class ChatReglerTests(TestCase):

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.operator = _bruker('ko1')

    def test_av_som_standard(self):
        self.assertFalse(services.chat_tillatt())

    def test_bryteren_leses_fra_appsetting(self):
        AppSetting.set(services.CHAT_NOKKEL, 'true')
        self.assertTrue(services.chat_tillatt())
        AppSetting.set(services.CHAT_NOKKEL, 'false')
        self.assertFalse(services.chat_tillatt())

    def test_uformell_avvises_naar_chatten_er_av(self):
        """Sperren står i tjenestelaget, ikke bare i skjemaet."""
        with self.assertRaises(services.Ugyldig):
            services.skriv_linje(self.vakt, 'kaffe?', bruker=self.operator, uformell=True)
        self.assertEqual(Logglinje.objects.count(), 0)

    def test_uformell_lagres_naar_chatten_er_paa(self):
        AppSetting.set(services.CHAT_NOKKEL, 'true')
        linje = services.skriv_linje(self.vakt, 'kaffe?', bruker=self.operator, uformell=True)
        self.assertTrue(linje.uformell)
        vanlig = services.skriv_linje(self.vakt, 'O1 framme', bruker=self.operator)
        self.assertFalse(vanlig.uformell)

    def test_retting_arver_merket(self):
        AppSetting.set(services.CHAT_NOKKEL, 'true')
        linje = services.skriv_linje(self.vakt, 'kaffe?', bruker=self.operator, uformell=True)
        # Bryteren av etterpå: rettingen skal likevel gå — linja *er* chat.
        AppSetting.set(services.CHAT_NOKKEL, 'false')
        ny = services.korriger(linje, bruker=self.operator, tekst='kaffe? ja takk')
        self.assertTrue(ny.uformell)

    def test_bryteren_er_audit_logget(self):
        """Noe et menneske har bestemt, ikke noe maskinen har talt."""
        from core.signals import nokkel_logges
        self.assertTrue(nokkel_logges(services.CHAT_NOKKEL))


class AnsvarsmerkeTests(TestCase):

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.operator = _bruker('ko1')

    def test_sett_og_les(self):
        self.assertEqual(services.ansvar_for(self.operator), '')
        services.sett_ansvar(self.operator, 'samband')
        self.assertEqual(services.ansvar_for(self.operator), 'samband')
        services.sett_ansvar(self.operator, '')
        self.assertEqual(services.ansvar_for(self.operator), '')
        self.assertEqual(Ansvarsmerke.objects.filter(bruker=self.operator).count(), 1,
                         'én rad per konto, oppdatert og ikke lagt til')

    def test_ukjent_omraade_avvises_og_store_bokstaver_normaliseres(self):
        with self.assertRaises(services.Ugyldig):
            services.sett_ansvar(self.operator, 'kantine')
        services.sett_ansvar(self.operator, ' Samband ')
        self.assertEqual(services.ansvar_for(self.operator), 'samband')

    def test_stemples_paa_linja(self):
        """§5.1: «ført av Kari, samband» — uten at hun skriver det hver gang."""
        services.sett_ansvar(self.operator, 'samband')
        linje = services.skriv_linje(self.vakt, 'x', bruker=self.operator)
        self.assertEqual(linje.ansvarsomraade, 'samband')

    def test_oppgitt_verdi_vinner_over_merket(self):
        services.sett_ansvar(self.operator, 'samband')
        linje = services.skriv_linje(self.vakt, 'x', bruker=self.operator,
                                     ansvarsomraade='media')
        self.assertEqual(linje.ansvarsomraade, 'media')
        tom = services.skriv_linje(self.vakt, 'y', bruker=self.operator, ansvarsomraade='')
        self.assertEqual(tom.ansvarsomraade, '', 'tom streng er et valg, ikke fravær')

    def test_merket_er_ikke_i_backupen(self):
        from core.backup import all_handlers, registrer_alle_moduler
        registrer_alle_moduler()
        ko = next(h for h in all_handlers() if h.slug == 'ko')
        self.assertNotIn('ko.Ansvarsmerke', ko.get_restore_models())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(TestCase):

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.leser = _gi(_bruker('leser'), 'ko', 'les')
        self.operator = _gi(_bruker('ko1'), 'ko', 'skriv_full')

    def _klient(self, bruker):
        c = Client()
        c.force_login(bruker)
        return c

    def _post(self, bruker, sti, kropp):
        return self._klient(bruker).post(sti, data=json.dumps(kropp),
                                         content_type='application/json')

    def test_les_kan_sette_eget_ansvar(self):
        """Merket styrer ingenting, så `les` holder — den som bare leser kan
        likevel ha ansvar for samband."""
        svar = self._post(self.leser, '/ko/api/ansvar/', {'omraade': 'samband'})
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(services.ansvar_for(self.leser), 'samband')

    def test_ukjent_omraade_er_400(self):
        self.assertEqual(self._post(self.leser, '/ko/api/ansvar/', {'omraade': 'x'}).status_code, 400)

    def test_anonym_avvises(self):
        svar = Client().post('/ko/api/ansvar/', data='{}', content_type='application/json')
        self.assertIn(svar.status_code, (302, 403))

    def test_sidebaren_baerer_ansvaret(self):
        services.sett_ansvar(self.operator, 'ressurser')
        self._klient(self.operator)   # logger inn → en sesjon
        rader = {r['brukernavn']: r for r in tilstede()}
        self.assertEqual(rader['ko1']['ansvar'], 'ressurser')

    def test_uformell_gjennom_api_et(self):
        svar = self._post(self.operator, '/ko/api/logg/ny/', {'tekst': 'kaffe', 'uformell': True})
        self.assertEqual(svar.status_code, 400, 'chatten er av')
        AppSetting.set(services.CHAT_NOKKEL, 'true')
        svar = self._post(self.operator, '/ko/api/logg/ny/', {'tekst': 'kaffe', 'uformell': True})
        self.assertEqual(svar.status_code, 201)
        self.assertTrue(svar.json()['data']['uformell'])

    def test_sida_baerer_bryteren_og_merket(self):
        c = self._klient(self.operator)
        html = c.get('/ko/').content.decode()
        self.assertNotIn('id="ko-logg-uformell"', html, 'avkryssingen finnes ikke når chatten er av')
        self.assertIn('id="ko-ansvar"', html)
        AppSetting.set(services.CHAT_NOKKEL, 'true')
        services.sett_ansvar(self.operator, 'media')
        html = c.get('/ko/').content.decode()
        self.assertIn('id="ko-logg-uformell"', html)
        self.assertIn('<option value="media" selected>', html)

    def test_vaktlisteflata_gates_av_vaktlista(self):
        """Komposisjonsregelen: vaktlistas data, lånt inn, krever vaktliste-`les`."""
        _gi(self.operator, 'oppdrag', 'les')
        c = self._klient(self.operator)
        self.assertNotIn('id="vaktliste-ressurser"', c.get('/ko/').content.decode())
        _gi(self.operator, 'vaktliste', 'les')
        self.assertIn('id="vaktliste-ressurser"', c.get('/ko/').content.decode())


class InnstillingsbryterenTests(TestCase):
    """Bryteren gjennom handleren, som `ko/tests_innstillinger.py` gjør for
    fristen. Sida selv er `core/tests_registre.py` sitt ansvar.

    **En avkryssing sendes bare når den er krysset av**, så «fraværende» må
    leses sammen med det skjulte følgefeltet `ko_chat_sendt`: har sida feltet,
    betyr fravær «av»; har den det ikke, betyr det «rør ikke».
    """

    def setUp(self):
        from ko.portalinnstillinger import KoInnstillinger
        self.handler = KoInnstillinger()

    def _send(self, **post):
        self.handler.lagre(self.handler.valider(post))

    def test_avkryssing_slaar_paa(self):
        self._send(ko_chat_sendt='1', ko_chat_tillatt='1')
        self.assertTrue(services.chat_tillatt())

    def test_ukrysset_slaar_av_naar_sida_hadde_feltet(self):
        AppSetting.set(services.CHAT_NOKKEL, 'true')
        self._send(ko_chat_sendt='1')
        self.assertFalse(services.chat_tillatt())

    def test_fravaerende_felt_beholder_verdien(self):
        """En innsending uten feltet — eldre mal, et skript — skal ikke slå
        chatten av i stillhet."""
        AppSetting.set(services.CHAT_NOKKEL, 'true')
        self._send()
        self.assertTrue(services.chat_tillatt())

    def test_fristen_lagres_fortsatt_ved_siden_av(self):
        self._send(ko_chat_sendt='1', ko_chat_tillatt='1', ko_logg_dager='365')
        self.assertEqual(services.oppbevaringsdager(), 365)
        self.assertTrue(services.chat_tillatt())
