"""KO-innstillinger, 18. sep. 2026: nullstilling og ansvarsområdene som liste.

«Det skal gå an for test og utvikling. På prod så står admin ansvarlig for
databehandlingen» (André). Reglene i tjenestelaget prøves tungt — en
nullstilling som tar med seg feil vakt er en feil ingen ser før loggen
mangler — og portene som porter: global admin, `confirm`, auditrad.
"""
from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from audit.models import AuditLog
from core.models import AppSetting
from core.vakt import hent_aktiv_vakt, vakt_for_year
from ko import services
from ko.models import Ansvarsmerke, Ansvarsomraade, Hendelse, Logglinje
from oppdrag import choices
from oppdrag import services as oservices
from oppdrag.models import Enhet, Lokasjon, Oppdrag, Statusmelding


def _bruker(navn, **kwargs):
    return CustomUser.objects.create_user(
        username=navn, password='x', must_change_password=False, **kwargs)


def _gi(bruker, modul, nivaa):
    ModulTilgang.objects.update_or_create(
        bruker=bruker, modul_slug=modul, defaults={'nivaa': nivaa})
    return bruker


class _Grunnlag(TestCase):

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.annen = vakt_for_year(2031)
        self.operator = _bruker('ko1')
        self.enhet = Enhet.objects.create(navn='HGSD 56', pa_vakt=True)
        self.lokasjon = Lokasjon.objects.create(navn='Scene sør')

    def _oppdrag(self, vakt=None, status=None):
        vakt = vakt or self.vakt
        o = Oppdrag.objects.create(
            vakt=vakt, oppdragsnummer=oservices.neste_oppdragsnummer(vakt),
            enhet=self.enhet, lokasjon=self.lokasjon, problemstilling='Fall',
            hastegrad=choices.HASTEGRAD[0])
        for st in status or ():
            oservices.sett_status(o, st, bruker=self.operator, enhet=self.enhet)
        return o

    def _hendelse(self, vakt=None):
        return services.opprett_hendelse(vakt or self.vakt, 'H', bruker=self.operator)


class NullstillOppdragTests(_Grunnlag):

    def test_sletter_alle_i_vakta_og_telleren(self):
        self._oppdrag(status=['rykker_ut', 'fremme'])
        self._oppdrag()
        self.assertEqual(oservices.nullstill_vakt(self.vakt), 2)
        self.assertEqual(Oppdrag.objects.filter(vakt=self.vakt).count(), 0)
        self.assertEqual(Statusmelding.objects.count(), 0, 'meldingene gikk med')
        self.assertEqual(self._oppdrag().oppdragsnummer, 1, 'O-serien starter på 1 igjen')

    def test_roerer_ikke_andre_vakter(self):
        andre = self._oppdrag(vakt=self.annen)
        self._oppdrag()
        oservices.nullstill_vakt(self.vakt)
        self.assertTrue(Oppdrag.objects.filter(pk=andre.pk).exists())
        self.assertTrue(AppSetting.objects.filter(key=oservices._nummer_nokkel(self.annen)).exists())

    def test_hendelsene_og_enhetene_staar(self):
        h = self._hendelse()
        o = self._oppdrag()
        services.knytt_oppdrag(o, h, bruker=self.operator)
        oservices.nullstill_vakt(self.vakt)
        self.assertTrue(Hendelse.objects.filter(pk=h.pk).exists())
        self.assertTrue(Enhet.objects.filter(pk=self.enhet.pk).exists())


class NullstillHendelserTests(_Grunnlag):

    def test_sletter_hendelsene_og_telleren_linjene_staar(self):
        h = self._hendelse()
        o = self._oppdrag()
        services.knytt_oppdrag(o, h, bruker=self.operator)
        linje = services.skriv_linje(self.vakt, 'kommentar', bruker=self.operator, hendelse=h)
        self.assertEqual(services.nullstill_hendelser(self.vakt), 1)
        self.assertEqual(Hendelse.objects.filter(vakt=self.vakt).count(), 0)
        linje.refresh_from_db(); o.refresh_from_db()
        self.assertIsNone(linje.hendelse_id, 'linja står, uten H-merket')
        self.assertIsNone(o.hendelse_id, 'oppdraget står, uten hendelsen')
        self.assertEqual(self._hendelse().hendelsesnummer, 1, 'H-serien starter på 1 igjen')

    def test_roerer_ikke_andre_vakter(self):
        andre = self._hendelse(vakt=self.annen)
        self._hendelse()
        services.nullstill_hendelser(self.vakt)
        self.assertTrue(Hendelse.objects.filter(pk=andre.pk).exists())
        self.assertTrue(AppSetting.objects.filter(key=services._hendelsesnokkel(self.annen)).exists())


class NullstillLoggTests(_Grunnlag):

    def test_sletter_linjene_ogsaa_rettede_og_systemlinjer(self):
        h = self._hendelse()   # gir en systemlinje
        linje = services.skriv_linje(self.vakt, 'a', bruker=self.operator)
        services.korriger(linje, bruker=self.operator, tekst='b')
        self.assertEqual(services.nullstill_logg(self.vakt), 3)
        self.assertEqual(Logglinje.objects.filter(vakt=self.vakt).count(), 0)
        self.assertTrue(Hendelse.objects.filter(pk=h.pk).exists(), 'hendelsene står')

    def test_roerer_ikke_andre_vakter(self):
        andre = services.skriv_linje(self.annen, 'x', bruker=self.operator)
        services.skriv_linje(self.vakt, 'y', bruker=self.operator)
        services.nullstill_logg(self.vakt)
        self.assertTrue(Logglinje.objects.filter(pk=andre.pk).exists())


class AnsvarsomraadeneTests(_Grunnlag):
    """Var en fast tuppel; nå en liste. Merket er fortsatt tekst."""

    def test_de_fire_er_seedet(self):
        self.assertEqual(services.ansvarsomraader_aktive(), ['samband', 'ressurser', 'logg', 'media'])

    def test_deaktivert_og_ukjent_avvises(self):
        Ansvarsomraade.objects.filter(navn='media').update(er_aktiv=False)
        with self.assertRaises(services.Ugyldig):
            services.sett_ansvar(self.operator, 'media')
        with self.assertRaises(services.Ugyldig):
            services.sett_ansvar(self.operator, 'kaffe')
        self.assertEqual(services.sett_ansvar(self.operator, ''), '')

    def test_nytt_omraade_kan_velges_med_listas_stavemaate(self):
        Ansvarsomraade.objects.create(navn='Sykestue', rekkefolge=50)
        self.assertEqual(services.sett_ansvar(self.operator, 'sykestue'), 'Sykestue')
        self.assertEqual(Ansvarsmerke.objects.get(bruker=self.operator).omraade, 'Sykestue')

    def test_omdoeping_skriver_ikke_om_loggen(self):
        services.sett_ansvar(self.operator, 'samband')
        linje = services.skriv_linje(self.vakt, 'x', bruker=self.operator)
        Ansvarsomraade.objects.filter(navn='samband').update(navn='Samband 2')
        linje.refresh_from_db()
        self.assertEqual(linje.ansvarsomraade, 'samband')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(TestCase):

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.leder = _gi(_bruker('leder'), 'ko', 'skriv_leder')
        _gi(self.leder, 'oppdrag', 'skriv_leder')
        self.sjef = _bruker('sjef', role='admin')
        self.enhet = Enhet.objects.create(navn='HGSD 56', pa_vakt=True)
        self.lokasjon = Lokasjon.objects.create(navn='Scene')

    def _post(self, bruker, sti, kropp=None, metode='post'):
        c = Client(); c.force_login(bruker)
        return getattr(c, metode)(sti, data=json.dumps(kropp or {}), content_type='application/json')

    def test_nullstill_er_global_admin_med_confirm_og_auditrad(self):
        services.opprett_hendelse(self.vakt, 'H', bruker=self.leder)
        Oppdrag.objects.create(vakt=self.vakt, oppdragsnummer=1, enhet=self.enhet,
                               lokasjon=self.lokasjon, problemstilling='Fall',
                               hastegrad=choices.HASTEGRAD[0])
        for hva in ('oppdrag', 'hendelser', 'logg'):
            with self.subTest(hva=hva):
                self.assertEqual(self._post(self.leder, f'/ko/api/nullstill/{hva}/', {'confirm': True}).status_code, 403,
                                 'KO-leder er ikke nok')
                self.assertEqual(self._post(self.sjef, f'/ko/api/nullstill/{hva}/').status_code, 400, 'confirm')
        self.assertEqual(self._post(self.sjef, '/ko/api/nullstill/kaffe/', {'confirm': True}).status_code, 404)
        svar = self._post(self.sjef, '/ko/api/nullstill/oppdrag/', {'confirm': True})
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertEqual(svar.json()['antall'], 1)
        self.assertEqual(Oppdrag.objects.count(), 0)
        rad = AuditLog.objects.filter(table_name='ko_nullstill_oppdrag').get()
        self.assertEqual(rad.user, self.sjef)
        self.assertIn('1 oppdrag', rad.new_value)
        self.assertEqual(self._post(self.sjef, '/ko/api/nullstill/hendelser/', {'confirm': True}).json()['antall'], 1)
        self.assertGreaterEqual(self._post(self.sjef, '/ko/api/nullstill/logg/', {'confirm': True}).json()['antall'], 1)
        self.assertEqual(Logglinje.objects.count(), 0)

    def test_ansvarsomraadene_er_en_liste_med_portene_fra_verdilistene(self):
        c = Client(); c.force_login(self.leder)
        self.assertEqual([r['navn'] for r in c.get('/ko/api/ansvarsomraader/').json()['data']],
                         ['samband', 'ressurser', 'logg', 'media'])
        svar = self._post(self.leder, '/ko/api/ansvarsomraader/', {'navn': 'Sykestue'})
        self.assertEqual(svar.status_code, 200, svar.content)
        pk = svar.json()['data']['id']
        self.assertEqual(self._post(self.leder, '/ko/api/ansvarsomraader/', {'navn': 'SAMBAND'}).status_code, 400,
                         'finnes alt, uansett bokstaver')
        self.assertIn('Sykestue', c.get('/ko/').content.decode(), 'nedtrekket i toppen følger lista')
        # I bruk = kontoer som bærer merket.
        services.sett_ansvar(self.leder, 'sykestue')
        self.assertEqual(self._post(self.sjef, f'/ko/api/ansvarsomraader/{pk}/', {'confirm': True}, 'delete').status_code, 409)
        services.sett_ansvar(self.leder, '')
        self.assertEqual(self._post(self.sjef, f'/ko/api/ansvarsomraader/{pk}/', {'confirm': True}, 'delete').status_code, 200)

    def test_fanene_paa_sida(self):
        c = Client(); c.force_login(self.leder)
        html = c.get('/ko/').content.decode()
        self.assertIn('data-verdifane="ansvarsomraader"', html)
        self.assertNotIn('data-verdifane="nullstill"', html, 'Nullstill er global admin')
        c.force_login(self.sjef)
        html = c.get('/ko/').content.decode()
        self.assertIn('data-verdifane="nullstill"', html)
        self.assertIn('koTegnNullstill', html)
