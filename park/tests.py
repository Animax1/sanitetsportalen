"""Park-modulen — tjenestelaget, porten uten innlogging, og rammeverket.

**Tyngden ligger på `services` og på porten** (`CLAUDE.md`, «Mutasjonstesting»):
en feil i forhåndsvalget legger seg i statistikken og merkes aldri, og en feil i
porten er et hull på portalens første side uten innlogging. Prøvene av porten
går gjennom de ekte endepunktene, med headerne siden sender.
"""
from __future__ import annotations

import ast
import re
import uuid
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from audit.models import AuditLog
from core.models import AppSetting, ModuleSettings
from core.tests_ratelimit import nok_til_a_bryte
from core.vakt import hent_aktiv_vakt
from ko import tavle
from ko.models import Tavleplassering
from ko.tests_hendelseslogg import skift
from oppdrag.models import Lokasjon
from vaktliste.models import Ressursgruppe, Vaktliste
from vaktliste.test_helpers import LAG, SAMLEPLASS, gruppe, lag_ressurs

from . import services, views_lag
from .models import Parklenke, Problemstilling, Registrering, Utfall


def _bruker(navn, **kw):
    return CustomUser.objects.create_user(username=navn, password='x',
                                          must_change_password=False, **kw)


def _gi(bruker, nivaa):
    ModulTilgang.objects.update_or_create(bruker=bruker, modul_slug='park',
                                          defaults={'nivaa': nivaa})
    return bruker


class _Grunnlag(TestCase):
    """En vakt, en vaktliste med to lag og en samleplass, to steder, en lenke."""

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.vl = Vaktliste.objects.create(vakt=self.vakt)
        # «Lag» registrerer i park fra migrasjon 0025; samleplassen gjør ikke.
        self.lag1 = lag_ressurs(vaktliste=self.vl, navn='Sandnes 2.1', gruppe=gruppe(LAG))
        self.lag2 = lag_ressurs(vaktliste=self.vl, navn='Sandnes 2.2', gruppe=gruppe(LAG))
        self.samleplass = lag_ressurs(vaktliste=self.vl, navn='Samleplass', gruppe=gruppe(SAMLEPLASS))
        self.park = Lokasjon.objects.create(navn='Parkscene')
        self.club = Lokasjon.objects.create(navn='Club')
        naa = timezone.now()
        self.lenke, self.token = services.lag_lenke(
            navn='Tiltakskort', aapen_fra=naa - timedelta(hours=1),
            aapen_til=naa + timedelta(hours=10))
        self.ps = Problemstilling.objects.get(navn='Skade bein/fot')
        self.utfall = Utfall.objects.get(navn='Behandlet på stedet')

    def _data(self, **over):
        data = {'lag': self.lag1.pk, 'sted': self.park.pk, 'problemstilling': self.ps.pk,
                'antall': 1, 'utfall': self.utfall.pk, 'idempotency_key': str(uuid.uuid4())}
        data.update(over)
        return data

    def _registrer(self, **over):
        rad, _ = services.registrer(self.lenke, self.vakt, self._data(**over))
        return rad


# ── Rutingflagget og startverdiene ───────────────────────────────────────────

class StartverdierTests(TestCase):

    def test_lag_registrerer_i_park_og_ingen_andre(self):
        self.assertEqual(
            list(Ressursgruppe.objects.filter(registrerer_i_park=True).values_list('navn', flat=True)),
            ['Lag'])

    def test_behandlet_paa_stedet_staar_oeverst(self):
        self.assertEqual(Utfall.objects.first().navn, 'Behandlet på stedet')

    def test_problemstillingene_er_pasientmodulens_som_start(self):
        from patients.choices import PROBLEMSTILLING
        self.assertEqual(list(Problemstilling.objects.values_list('navn', flat=True)),
                         list(PROBLEMSTILLING))


# ── Lenken ───────────────────────────────────────────────────────────────────

class LenkenTests(_Grunnlag):

    def test_tokenet_lagres_ikke_bare_hashen(self):
        self.assertNotEqual(self.lenke.hemmelighet_hash, self.token)
        self.assertEqual(self.lenke.hemmelighet_hash, services.hash_token(self.token))
        self.assertFalse(Parklenke.objects.filter(hemmelighet_hash=self.token).exists())

    def test_tokenet_er_langt_nok(self):
        self.assertGreaterEqual(len(self.token), 43, '32 byte i base64 — ikke gjettbart')

    def test_gyldig_lenke_innenfor_oppetiden(self):
        self.assertEqual(services.aapen_lenke(self.token), self.lenke)

    def test_feil_token(self):
        self.assertIsNone(services.aapen_lenke(self.token + 'x'))
        self.assertIsNone(services.aapen_lenke(''))
        self.assertIsNone(services.aapen_lenke(None))

    def test_foer_og_ved_slutten_av_oppetiden(self):
        self.assertIsNone(services.aapen_lenke(self.token, naa=self.lenke.aapen_fra - timedelta(seconds=1)))
        self.assertEqual(services.aapen_lenke(self.token, naa=self.lenke.aapen_fra), self.lenke)
        self.assertIsNone(services.aapen_lenke(self.token, naa=self.lenke.aapen_til),
                          'til er utenfor — en lenke som stenger kl. 08 er stengt kl. 08')

    def test_fjernet_lenke(self):
        services.fjern_lenke(self.lenke)
        self.assertIsNone(services.aapen_lenke(self.token))

    def test_modulen_slaatt_av(self):
        ModuleSettings.objects.filter(slug='park').update(enabled=False)
        self.assertIsNone(services.aapen_lenke(self.token))

    def test_avsluttet_vakt(self):
        type(self.vakt).objects.filter(pk=self.vakt.pk).update(avsluttet=timezone.now())
        self.assertIsNone(services.aapen_lenke(self.token))

    def test_til_maa_vaere_etter_fra(self):
        naa = timezone.now()
        with self.assertRaises(services.Ugyldig):
            services.lag_lenke(navn='x', aapen_fra=naa, aapen_til=naa)
        with self.assertRaises(services.Ugyldig):
            services.lag_lenke(navn='  ', aapen_fra=naa, aapen_til=naa + timedelta(hours=1))

    def test_opprettelse_og_fjerning_logges_uten_hash(self):
        rader = AuditLog.objects.filter(table_name='park_parklenke', record_id=self.lenke.pk)
        self.assertEqual(rader.count(), 1)
        self.assertNotIn(self.lenke.hemmelighet_hash, rader.get().new_value or '')
        services.fjern_lenke(self.lenke)
        services.fjern_lenke(self.lenke)
        self.assertEqual(rader.filter(field_name='fjernet').count(), 1, 'fjerning er idempotent')


# ── Lagene ───────────────────────────────────────────────────────────────────

class LageneTests(_Grunnlag):

    def test_bare_grupper_med_flagget(self):
        self.assertEqual([r.navn for r in services.lagene()], ['Sandnes 2.1', 'Sandnes 2.2'])

    def test_inaktiv_gruppe_er_ute(self):
        Ressursgruppe.objects.filter(navn=LAG).update(er_aktiv=False)
        self.assertEqual(list(services.lagene()), [])

    def test_flagget_paa_en_annen_gruppe_tar_den_med(self):
        Ressursgruppe.objects.filter(navn=SAMLEPLASS).update(registrerer_i_park=True)
        self.assertIn(self.samleplass, services.lagene())


# ── Forhåndsvalget (B19): nyeste vinner ──────────────────────────────────────

class ForhandsvalgTests(_Grunnlag):

    def setUp(self):
        super().setUp()
        skift(self.lag1)   # tavla plasserer bare lag som er på vakt nå

    def _plasser(self, lokasjon, fra):
        tavle.plasser(self.vakt, self.lag1, bruker=None, lokasjon=lokasjon)
        Tavleplassering.objects.filter(ressurs=self.lag1, til__isnull=True).update(fra=fra)

    def _registrert(self, lokasjon, tid):
        rad = self._registrer(sted=lokasjon.pk)
        Registrering.objects.filter(pk=rad.pk).update(registrert_at=tid)
        return rad

    def test_ingenting(self):
        self.assertEqual(services.forhandsvalg(self.vakt, self.lag1.pk)['kilde'], 'ingen')

    def test_bare_registrering(self):
        self._registrert(self.club, timezone.now())
        v = services.forhandsvalg(self.vakt, self.lag1.pk)
        self.assertEqual((v['kilde'], v['lokasjon_id']), ('registrering', self.club.pk))

    def test_bare_ko(self):
        self._plasser(self.park, timezone.now())
        v = services.forhandsvalg(self.vakt, self.lag1.pk)
        self.assertEqual((v['kilde'], v['lokasjon_id']), ('ko', self.park.pk))

    def test_ko_nyere_enn_registreringen_vinner(self):
        naa = timezone.now()
        self._registrert(self.club, naa - timedelta(minutes=30))
        self._plasser(self.park, naa - timedelta(minutes=5))
        v = services.forhandsvalg(self.vakt, self.lag1.pk)
        self.assertEqual((v['kilde'], v['lokasjon_id']), ('ko', self.park.pk))

    def test_registrering_nyere_enn_ko_vinner(self):
        naa = timezone.now()
        self._plasser(self.park, naa - timedelta(minutes=30))
        self._registrert(self.club, naa - timedelta(minutes=5))
        v = services.forhandsvalg(self.vakt, self.lag1.pk)
        self.assertEqual((v['kilde'], v['lokasjon_id']), ('registrering', self.club.pk))

    def test_likt_vinner_registreringen(self):
        t = timezone.now() - timedelta(minutes=5)
        self._plasser(self.park, t)
        self._registrert(self.club, t)
        self.assertEqual(services.forhandsvalg(self.vakt, self.lag1.pk)['kilde'], 'registrering')

    def test_bryteren_av_fjerner_ko(self):
        """RISIKOVALG(park-ko-posisjon): av = aldri KO-kilden."""
        naa = timezone.now()
        self._registrert(self.club, naa - timedelta(minutes=30))
        self._plasser(self.park, naa)
        AppSetting.set(services.KO_POSISJON_NOKKEL, 'false')
        v = services.forhandsvalg(self.vakt, self.lag1.pk)
        self.assertEqual((v['kilde'], v['lokasjon_id']), ('registrering', self.club.pk))
        AppSetting.objects.filter(key=services.KO_POSISJON_NOKKEL).delete()
        self.assertTrue(services.ko_posisjon_paa(), 'uten rad er bryteren på')

    def test_ko_modulen_av_teller_ikke(self):
        self._plasser(self.park, timezone.now())
        ModuleSettings.objects.filter(slug='ko').update(enabled=False)
        self.assertEqual(services.forhandsvalg(self.vakt, self.lag1.pk)['kilde'], 'ingen')

    def test_pause_er_ikke_et_sted(self):
        tavle.plasser(self.vakt, self.lag1, bruker=None, pause=True)
        self.assertEqual(services.forhandsvalg(self.vakt, self.lag1.pk)['kilde'], 'ingen')

    def test_deaktivert_sted_er_ingen_kandidat(self):
        naa = timezone.now()
        self._registrert(self.club, naa - timedelta(minutes=30))
        self._plasser(self.park, naa)
        Lokasjon.objects.filter(pk=self.park.pk).update(er_aktiv=False)
        v = services.forhandsvalg(self.vakt, self.lag1.pk)
        self.assertEqual((v['kilde'], v['lokasjon_id']), ('registrering', self.club.pk))

    def test_slettet_registrering_teller_ikke(self):
        rad = self._registrert(self.club, timezone.now())
        Registrering.objects.filter(pk=rad.pk).update(slettet_at=timezone.now())
        self.assertEqual(services.forhandsvalg(self.vakt, self.lag1.pk)['kilde'], 'ingen')

    def test_et_annet_lags_registrering_teller_ikke(self):
        self._registrer(lag=self.lag2.pk, sted=self.club.pk)
        self.assertEqual(services.forhandsvalg(self.vakt, self.lag1.pk)['kilde'], 'ingen')

    def test_en_feilende_ko_kilde_gir_ikke_500(self):
        self._registrert(self.club, timezone.now() - timedelta(hours=1))
        with mock.patch('ko.ressursplassering.KoRessursplassering.aapen_plassering',
                        side_effect=RuntimeError('treg tavle')):
            v = services.forhandsvalg(self.vakt, self.lag1.pk)
        self.assertEqual(v['kilde'], 'registrering')


# ── Registreringen ───────────────────────────────────────────────────────────

class RegistreringTests(_Grunnlag):

    def test_lagrer_med_frosne_navn(self):
        rad = self._registrer(antall=3)
        self.assertEqual((rad.ressurs_navn, rad.lokasjon_navn, rad.problemstilling, rad.utfall, rad.antall),
                         ('Sandnes 2.1', 'Parkscene', 'Skade bein/fot', 'Behandlet på stedet', 3))
        self.assertEqual(rad.vakt, self.vakt)
        self.assertEqual(rad.lenke, self.lenke)

    def test_samme_nokkel_gir_en_rad(self):
        data = self._data()
        a, ny_a = services.registrer(self.lenke, self.vakt, data)
        b, ny_b = services.registrer(self.lenke, self.vakt, dict(data, antall=5))
        self.assertEqual((a.pk, ny_a, ny_b), (b.pk, True, False))
        self.assertEqual(Registrering.objects.count(), 1)

    def test_en_ny_sending_etter_at_lista_er_endret_gir_kvitteringen(self):
        """Telefonen mistet svaret og sender igjen — i mellomtiden har noen
        deaktivert problemstillingen. Registreringen *er* lagret, og laget skal
        få kvitteringen, ikke en feilmelding som får det til å registrere på
        nytt."""
        data = self._data()
        a, _ = services.registrer(self.lenke, self.vakt, data)
        Problemstilling.objects.filter(pk=self.ps.pk).update(er_aktiv=False)
        b, ny = services.registrer(self.lenke, self.vakt, data)
        self.assertEqual((b.pk, ny), (a.pk, False))

    def test_lag_uten_flagget_avvises(self):
        with self.assertRaises(services.Ugyldig):
            self._registrer(lag=self.samleplass.pk)

    def test_inaktive_verdier_avvises(self):
        Problemstilling.objects.filter(pk=self.ps.pk).update(er_aktiv=False)
        with self.assertRaises(services.Ugyldig):
            self._registrer()
        Problemstilling.objects.filter(pk=self.ps.pk).update(er_aktiv=True)
        Utfall.objects.filter(pk=self.utfall.pk).update(er_aktiv=False)
        with self.assertRaises(services.Ugyldig):
            self._registrer()
        Utfall.objects.filter(pk=self.utfall.pk).update(er_aktiv=True)
        Lokasjon.objects.filter(pk=self.park.pk).update(er_aktiv=False)
        with self.assertRaises(services.Ugyldig):
            self._registrer()

    def test_antallets_grenser(self):
        self.assertEqual(self._registrer(antall=1).antall, 1)
        self.assertEqual(self._registrer(antall=99).antall, 99)
        for feil in (0, 100, -1, True, 'tre', None):
            with self.assertRaises(services.Ugyldig, msg=repr(feil)):
                self._registrer(antall=feil)

    def test_nokkelen_maa_vaere_en_uuid(self):
        for feil in ('', 'abc', None, 12):
            with self.assertRaises(services.Ugyldig, msg=repr(feil)):
                self._registrer(idempotency_key=feil)

    def test_maalingen(self):
        rad = self._registrer(forhandsvalg_kilde='ko', forhandsvalg_endret=True)
        self.assertEqual((rad.forhandsvalg_kilde, rad.forhandsvalg_endret), ('ko', True))
        rad = self._registrer(forhandsvalg_kilde='tull', forhandsvalg_endret='ja')
        self.assertEqual((rad.forhandsvalg_kilde, rad.forhandsvalg_endret), ('ingen', False))

    def test_lenken_faar_sist_brukt(self):
        self.assertIsNone(self.lenke.sist_brukt_at)
        self._registrer()
        self.lenke.refresh_from_db()
        self.assertIsNotNone(self.lenke.sist_brukt_at)

    def test_kvitteringen_har_ingen_andre_registreringer(self):
        self._registrer(lag=self.lag2.pk)
        rad = self._registrer()
        k = services.kvittering(rad, self.vakt)
        self.assertEqual(set(k), {'registrert_at', 'angre_til', 'lag', 'antall', 'problemstilling',
                                  'sted', 'utfall', 'antall_for_laget'})
        self.assertEqual(k['antall_for_laget'], 1, 'bare lagets egne telles')


class AngreTests(_Grunnlag):

    def test_innenfor_fristen(self):
        rad = self._registrer()
        services.angre(self.lenke, rad.idempotency_key)
        self.assertFalse(Registrering.objects.exists())

    def test_etter_fristen(self):
        rad = self._registrer()
        with self.assertRaises(services.Ugyldig):
            services.angre(self.lenke, rad.idempotency_key,
                           naa=rad.registrert_at + timedelta(minutes=5, seconds=1))
        services.angre(self.lenke, rad.idempotency_key,
                       naa=rad.registrert_at + timedelta(minutes=5))

    def test_fristen_styres_av_admin_og_klemmes(self):
        AppSetting.set(services.ANGREFRIST_NOKKEL, '10')
        rad = self._registrer()
        services.angre(self.lenke, rad.idempotency_key,
                       naa=rad.registrert_at + timedelta(minutes=9))
        AppSetting.set(services.ANGREFRIST_NOKKEL, '999')
        self.assertEqual(services.angrefrist_min(), services.ANGREFRIST_MAKS)
        AppSetting.set(services.ANGREFRIST_NOKKEL, 'tull')
        self.assertEqual(services.angrefrist_min(), services.ANGREFRIST_STANDARD)

    def test_en_annen_lenke_kan_ikke_angre(self):
        rad = self._registrer()
        naa = timezone.now()
        annen, _ = services.lag_lenke(navn='b', aapen_fra=naa, aapen_til=naa + timedelta(hours=1))
        with self.assertRaises(services.Ugyldig):
            services.angre(annen, rad.idempotency_key)

    def test_slettet_av_leder_kan_ikke_angres(self):
        rad = self._registrer()
        Registrering.objects.filter(pk=rad.pk).update(slettet_at=timezone.now())
        with self.assertRaises(services.Ugyldig):
            services.angre(self.lenke, rad.idempotency_key)


# ── Porten uten innlogging ───────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class PortenTests(_Grunnlag):

    def setUp(self):
        super().setUp()
        self.c = Client()
        self.telefon = str(uuid.uuid4())

    def _h(self, token=None, telefon=None):
        return {'HTTP_X_PARK_LENKE': self.token if token is None else token,
                'HTTP_X_PARK_TELEFON': self.telefon if telefon is None else telefon}

    def _post(self, navn, data, **h):
        import json
        return self.c.post(reverse(navn), data=json.dumps(data),
                           content_type='application/json', **self._h(**h))

    def test_siden_svarer_uten_innlogging_og_uten_data(self):
        svar = self.c.get(reverse('park_lag_side'))
        self.assertEqual(svar.status_code, 200)
        html = svar.content.decode()
        self.assertNotIn('Sandnes', html)
        self.assertIn('js/park-lag.', html)
        self.assertNotIn('portal-utils.js', html)
        self.assertIn('no-referrer', html)

    def test_uten_token_og_med_feil_token_samme_svar(self):
        a = self.c.get(reverse('park_lag_oppsett'), **self._h(token=''))
        b = self.c.get(reverse('park_lag_oppsett'), **self._h(token='feil'))
        services.fjern_lenke(self.lenke)
        c = self.c.get(reverse('park_lag_oppsett'), **self._h())
        self.assertEqual({a.status_code, b.status_code, c.status_code}, {403})
        self.assertEqual(a.json(), b.json())
        self.assertEqual(b.json(), c.json())

    def test_tokenet_i_stien_virker_ikke(self):
        svar = self.c.get(reverse('park_lag_oppsett') + f'?lenke={self.token}',
                          HTTP_X_PARK_TELEFON=self.telefon)
        self.assertEqual(svar.status_code, 403)

    def test_uten_telefon_id(self):
        self.assertEqual(self.c.get(reverse('park_lag_oppsett'), **self._h(telefon='')).status_code, 400)

    def test_oppsett_har_verdimengdene_og_ingen_registreringer(self):
        self._registrer()
        d = self.c.get(reverse('park_lag_oppsett'), **self._h()).json()
        self.assertEqual(set(d), {'vakt', 'lag', 'steder', 'problemstillinger', 'utfall',
                                  'angrefrist_min'})
        self.assertEqual([lag['navn'] for lag in d['lag']], ['Sandnes 2.1', 'Sandnes 2.2'])
        self.assertEqual(d['utfall'][0]['navn'], 'Behandlet på stedet')

    def test_sted_for_ett_lag(self):
        self._registrer(sted=self.club.pk)
        d = self.c.get(reverse('park_lag_sted') + f'?lag={self.lag1.pk}', **self._h()).json()
        self.assertEqual((d['sted'], d['kilde']), (self.club.pk, 'registrering'))
        self.assertEqual(self.c.get(reverse('park_lag_sted') + f'?lag={self.samleplass.pk}',
                                    **self._h()).status_code, 404)
        self.assertEqual(self.c.get(reverse('park_lag_sted') + '?lag=x',
                                    **self._h()).status_code, 400)

    def test_registrer_og_angre_gjennom_endepunktene(self):
        data = self._data()
        svar = self._post('park_lag_registrer', data)
        self.assertEqual(svar.status_code, 201)
        self.assertEqual(svar.json()['kvittering']['antall_for_laget'], 1)
        self.assertEqual(self._post('park_lag_registrer', data).status_code, 200, 'samme nøkkel')
        self.assertEqual(self._post('park_lag_angre', {'idempotency_key': data['idempotency_key']}).status_code, 200)
        self.assertFalse(Registrering.objects.exists())
        self.assertEqual(self._post('park_lag_angre', {'idempotency_key': data['idempotency_key']}).status_code, 409)

    def test_ugyldig_registrering_gir_400(self):
        self.assertEqual(self._post('park_lag_registrer', self._data(antall=0)).status_code, 400)

    def test_innlogget_portalbruker_uten_token_kommer_ikke_inn(self):
        admin = _bruker('adm', role='admin')
        self.c.force_login(admin)
        self.assertEqual(self.c.get(reverse('park_lag_oppsett'),
                                    HTTP_X_PARK_TELEFON=self.telefon).status_code, 403)

    def test_get_paa_registrer_avvises(self):
        self.assertEqual(self.c.get(reverse('park_lag_registrer'), **self._h()).status_code, 405)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=True)
class GrenseneTests(_Grunnlag):
    """§4.5: per telefon, et tak per lenke, og per IP bare for ugyldige."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()
        self.c = Client()

    def _hent(self, token, telefon, ip='10.0.0.1'):
        return self.c.get(reverse('park_lag_oppsett'), REMOTE_ADDR=ip,
                          HTTP_X_PARK_LENKE=token, HTTP_X_PARK_TELEFON=telefon).status_code

    def test_en_telefon_bremses_uten_aa_stenge_ute_de_andre(self):
        with mock.patch.object(views_lag, 'GRENSE_TELEFON', '5/m'):
            en = str(uuid.uuid4())
            koder = [self._hent(self.token, en) for _ in range(nok_til_a_bryte(5))]
            self.assertIn(429, koder)
            self.assertEqual(self._hent(self.token, str(uuid.uuid4())), 200,
                             'en annen telefon bak samme IP skal slippe til')

    def test_taket_per_lenke(self):
        with mock.patch.object(views_lag, 'GRENSE_LENKE', '5/m'):
            koder = [self._hent(self.token, str(uuid.uuid4())) for _ in range(nok_til_a_bryte(5))]
        self.assertIn(429, koder)

    def test_ugyldige_telles_per_ip(self):
        with mock.patch.object(views_lag, 'GRENSE_UGYLDIG', '5/m'):
            koder = [self._hent('feil', str(uuid.uuid4())) for _ in range(nok_til_a_bryte(5))]
            self.assertIn(429, koder)
            self.assertEqual(self._hent(self.token, str(uuid.uuid4())), 200,
                             'gyldige forsøk fra samme IP telles ikke i den bøtta')


# ── De innloggede flatene ────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class IndexTests(_Grunnlag):

    def test_uten_tilgang(self):
        c = Client()
        c.force_login(_bruker('ingen'))
        self.assertEqual(c.get('/park/').status_code, 403)

    def test_les_faar_henvisningen_og_ikke_oppsettet(self):
        c = Client()
        c.force_login(_gi(_bruker('les'), 'les'))
        html = c.get('/park/').content.decode()
        self.assertIn('/statistikk/', html)
        self.assertNotIn('park-oppsett.', html)
        self.assertNotIn('park-ny-lenke', html)

    def test_leder_faar_oppsettet(self):
        c = Client()
        c.force_login(_gi(_bruker('leder'), 'skriv_leder'))
        html = c.get('/park/').content.decode()
        self.assertIn('js/park-oppsett.', html)
        self.assertIn('id="park-ny-lenke"', html)
        self.assertIn('park: "skriv_leder"', html)
        self.assertIn('admin: false', html)


class _Oppsett(_Grunnlag):
    """Klientene for pulje 2: en leder, en som bare leser, og global admin."""

    def setUp(self):
        super().setUp()
        self.leder = Client()
        self.leder.force_login(_gi(_bruker('leder'), 'skriv_leder'))
        self.les = Client()
        self.les.force_login(_gi(_bruker('les'), 'les'))
        self.admin = Client()
        self.admin.force_login(_bruker('adm', role='admin'))

    def _post(self, c, url, data=None, metode='post'):
        import json
        return getattr(c, metode)(url, data=json.dumps(data or {}), content_type='application/json')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LenkeoppsettTests(_Oppsett):

    def _ny(self, c, **over):
        data = {'navn': 'Bliksund', 'aapen_fra': '2026-10-01T08:00', 'aapen_til': '2026-10-04T08:00'}
        data.update(over)
        return self._post(c, '/park/api/lenker/', data)

    def test_ny_lenke_viser_adressen_en_gang(self):
        svar = self._ny(self.leder)
        self.assertEqual(svar.status_code, 201)
        adresse = svar.json()['adresse']
        self.assertIn('/park/r/#', adresse)
        token = adresse.split('#', 1)[1]
        lenke = Parklenke.objects.get(navn='Bliksund')
        self.assertEqual(lenke.hemmelighet_hash, services.hash_token(token))
        self.assertEqual(lenke.opprettet_av_navn, 'leder')
        lista = self.leder.get('/park/api/lenker/').content.decode()
        self.assertNotIn(token, lista, 'adressen vises aldri igjen')
        self.assertNotIn(lenke.hemmelighet_hash, lista)

    def test_oppetiden_leses_som_norsk_tid(self):
        self._ny(self.leder)
        lenke = Parklenke.objects.get(navn='Bliksund')
        self.assertEqual(timezone.localtime(lenke.aapen_fra).strftime('%H:%M'), '08:00')

    def test_ugyldig_oppetid(self):
        self.assertEqual(self._ny(self.leder, aapen_til='2026-09-30T08:00').status_code, 400)
        self.assertEqual(self._ny(self.leder, aapen_fra='').status_code, 400)
        self.assertEqual(self._ny(self.leder, navn='').status_code, 400)

    def test_les_kan_hverken_se_eller_lage(self):
        self.assertEqual(self.les.get('/park/api/lenker/').status_code, 403)
        self.assertEqual(self._ny(self.les).status_code, 403)

    def test_fjern_krever_bekreftelse(self):
        url = f'/park/api/lenker/{self.lenke.pk}/fjern/'
        self.assertEqual(self._post(self.leder, url).status_code, 400)
        self.assertEqual(services.aapen_lenke(self.token), self.lenke)
        self.assertEqual(self._post(self.leder, url, {'confirm': True}).status_code, 200)
        self.assertIsNone(services.aapen_lenke(self.token))
        self.assertEqual(self._post(self.les, url, {'confirm': True}).status_code, 403)

    def test_lista_viser_status_og_antall(self):
        self._registrer()
        rad = next(l for l in self.leder.get('/park/api/lenker/').json()['data'] if l['id'] == self.lenke.pk)
        self.assertTrue(rad['aapen_naa'])
        self.assertEqual(rad['antall'], 1)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SlettingTests(_Oppsett):

    def test_slett_en_krever_grunn_og_raden_blir_staaende(self):
        rad = self._registrer()
        url = f'/park/api/registreringer/{rad.pk}/slett/'
        self.assertEqual(self._post(self.leder, url, {'grunn': '  '}).status_code, 400)
        self.assertEqual(self._post(self.les, url, {'grunn': 'x'}).status_code, 403)
        self.assertEqual(self._post(self.leder, url, {'grunn': 'Trykket feil lag'}).status_code, 200)
        rad.refresh_from_db()
        self.assertEqual((rad.slettet_grunn, rad.slettet_av_navn), ('Trykket feil lag', 'leder'))
        self.assertIsNotNone(rad.slettet_at)
        self.assertEqual(self._post(self.leder, url, {'grunn': 'igjen'}).status_code, 400)
        self.assertTrue(AuditLog.objects.filter(table_name='park_registrering', record_id=rad.pk,
                                                field_name='slettet').exists())

    def test_slettet_teller_ikke_for_laget(self):
        rad = self._registrer()
        services.slett_registrering(rad, bruker=None, grunn='feil')
        self.assertEqual(services.antall_for_laget(self.vakt, self.lag1.pk), 0)

    def test_lista_viser_de_slettede_merket(self):
        rad = self._registrer()
        services.slett_registrering(rad, bruker=None, grunn='feil')
        d = self.leder.get('/park/api/registreringer/').json()
        self.assertEqual([(r['id'], r['slettet']) for r in d['data']], [(rad.pk, True)])
        self.assertEqual(self.les.get('/park/api/registreringer/').status_code, 403)

    def test_slett_etter_viser_antallet_foer_det_sletter(self):
        naa = timezone.now()
        gammel = self._registrer()
        Registrering.objects.filter(pk=gammel.pk).update(registrert_at=naa - timedelta(hours=2))
        ny1, ny2 = self._registrer(), self._registrer()
        annen, _ = services.lag_lenke(navn='annen', aapen_fra=naa - timedelta(hours=1),
                                      aapen_til=naa + timedelta(hours=1))
        fra_annen, _ = services.registrer(annen, self.vakt, self._data())
        url = f'/park/api/lenker/{self.lenke.pk}/slett-etter/'
        etter = timezone.localtime(naa - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')

        svar = self._post(self.leder, url, {'etter': etter, 'grunn': 'lekket'})
        self.assertEqual((svar.status_code, svar.json()['antall']), (409, 2))
        self.assertFalse(Registrering.objects.filter(slettet_at__isnull=False).exists(),
                         'uten confirm slettes ingenting')

        self.assertEqual(self._post(self.leder, url, {'etter': etter, 'confirm': True}).status_code, 400,
                         'grunnen er påkrevd')
        svar = self._post(self.leder, url, {'etter': etter, 'grunn': 'lekket', 'confirm': True})
        self.assertEqual((svar.status_code, svar.json()['antall']), (200, 2))
        slettet = set(Registrering.objects.filter(slettet_at__isnull=False).values_list('pk', flat=True))
        self.assertEqual(slettet, {ny1.pk, ny2.pk}, 'bare denne lenken, bare etter tidspunktet')
        self.assertNotIn(fra_annen.pk, slettet)
        self.assertEqual(AuditLog.objects.filter(field_name='slettet_etter').count(), 1,
                         'én auditrad for én beslutning')
        self.assertEqual(self._post(self.les, url, {'etter': etter, 'grunn': 'x', 'confirm': True}).status_code, 403)

    def test_slett_etter_skriver_ikke_over_en_tidligere_sletting(self):
        """En rad som alt er slettet med sin egen grunn, skal beholde den — og
        ikke telles med i antallet den som rydder får se."""
        forst, andre = self._registrer(), self._registrer()
        services.slett_registrering(forst, bruker=None, grunn='feil lag')
        etter = timezone.now() - timedelta(hours=1)
        self.assertEqual(services.slett_fra_lenke(self.lenke, etter=etter, vakt=self.vakt,
                                                  bruker=None, grunn='lekket'), 1)
        forst.refresh_from_db()
        andre.refresh_from_db()
        self.assertEqual((forst.slettet_grunn, andre.slettet_grunn), ('feil lag', 'lekket'))

    def test_lista_henter_mer_enn_500(self):
        """«De blir fort mellom 500–1500» (André, 28. sep. 2026). Den eldste
        feilregistreringen skal kunne finnes og slettes."""
        rad = self._registrer()
        Registrering.objects.bulk_create([
            Registrering(vakt=self.vakt, lenke=self.lenke, ressurs_navn='Sandnes 2.1',
                         problemstilling='Kramper', utfall='Gikk videre selv', lokasjon_navn='Club',
                         idempotency_key=str(uuid.uuid4())) for _ in range(600)])
        d = self.leder.get('/park/api/registreringer/').json()
        self.assertEqual(len(d['data']), 601)
        self.assertIn(rad.pk, [r['id'] for r in d['data']])

    def test_slett_etter_uten_tidspunkt(self):
        url = f'/park/api/lenker/{self.lenke.pk}/slett-etter/'
        self.assertEqual(self._post(self.leder, url, {'grunn': 'x'}).status_code, 400)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VerdimengdeneTests(_Oppsett):

    def test_leder_setter_opp_problemstillinger(self):
        svar = self._post(self.leder, '/park/api/problemstillinger/', {'navn': 'Plaster'})
        self.assertEqual(svar.status_code, 200)
        self.assertIn('Plaster', [p.navn for p in services.problemstillinger()])
        self.assertEqual(self._post(self.les, '/park/api/problemstillinger/', {'navn': 'Vann'}).status_code, 403)

    def test_utfall_er_bare_admin(self):
        self.assertEqual(self._post(self.leder, '/park/api/utfall/', {'navn': 'Ny'}).status_code, 403)
        self.assertEqual(self._post(self.admin, '/park/api/utfall/', {'navn': 'Ny'}).status_code, 200)
        u = Utfall.objects.get(navn='Ny')
        self.assertEqual(self._post(self.leder, f'/park/api/utfall/{u.pk}/', {'er_aktiv': False},
                                    metode='put').status_code, 403)

    def test_i_bruk_kan_ikke_slettes(self):
        self._registrer()
        url = f'/park/api/problemstillinger/{self.ps.pk}/'
        self.assertEqual(self._post(self.admin, url, {'confirm': True}, metode='delete').status_code, 409)
        self.assertEqual(self._post(self.leder, url, {'confirm': True}, metode='delete').status_code, 403,
                         'sletting er global admin')

    def test_deaktivert_forsvinner_fra_siden(self):
        self._post(self.leder, f'/park/api/problemstillinger/{self.ps.pk}/', {'er_aktiv': False}, metode='put')
        self.assertNotIn(self.ps, services.problemstillinger())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SkjulteStederTests(_Oppsett):
    """«Det er enkelte lokasjoner som er uaktuelt for dem men ikke bil
    ressurser» (André, 28. sep. 2026). Parks regel, ikke oppdragsmodulens."""

    def _skjul(self, lok, verdi=True, c=None):
        return self._post(c or self.leder, f'/park/api/steder/{lok.pk}/skjul/', {'skjult': verdi})

    def test_skjult_sted_er_borte_fra_siden_og_avvises(self):
        self.assertEqual(self._skjul(self.club).status_code, 200)
        self.assertNotIn(self.club, services.steder())
        self.assertIn(self.park, services.steder())
        with self.assertRaises(services.Ugyldig):
            self._registrer(sted=self.club.pk)
        c = Client()
        d = c.get(reverse('park_lag_oppsett'), HTTP_X_PARK_LENKE=self.token,
                  HTTP_X_PARK_TELEFON=str(uuid.uuid4())).json()
        self.assertEqual([s['navn'] for s in d['steder']], ['Parkscene'])

    def test_bilene_ser_det_fortsatt(self):
        self._skjul(self.club)
        self.club.refresh_from_db()
        self.assertTrue(self.club.er_aktiv, 'lokasjonen i oppdrag røres ikke')

    def test_forhaandsvalget_hopper_over_et_skjult_sted(self):
        naa = timezone.now()
        rad = self._registrer(sted=self.park.pk)
        Registrering.objects.filter(pk=rad.pk).update(registrert_at=naa - timedelta(hours=1))
        skift(self.lag1)
        tavle.plasser(self.vakt, self.lag1, bruker=None, lokasjon=self.club)
        self.assertEqual(services.forhandsvalg(self.vakt, self.lag1.pk)['lokasjon_id'], self.club.pk)
        self._skjul(self.club)
        v = services.forhandsvalg(self.vakt, self.lag1.pk)
        self.assertEqual((v['kilde'], v['lokasjon_id']), ('registrering', self.park.pk))

    def test_gamle_registreringer_teller_fortsatt(self):
        from .statistikk import park_stats
        self._registrer(sted=self.club.pk, antall=3)
        self._skjul(self.club)
        self.assertEqual({s['navn']: s['kontakter'] for s in park_stats(self.vakt)['per_sted']},
                         {'Club': 3})

    def test_vis_igjen_og_idempotent_med_en_auditrad(self):
        self._skjul(self.club)
        self._skjul(self.club)
        self.assertEqual(AuditLog.objects.filter(table_name='park_skjultsted', field_name='skjult').count(), 1)
        self._skjul(self.club, False)
        self.assertIn(self.club, services.steder())
        self.assertEqual(AuditLog.objects.filter(table_name='park_skjultsted', field_name='vist').count(), 1)

    def test_bare_literal_true_skjuler(self):
        self._skjul(self.club, 'ja')
        self.assertIn(self.club, services.steder())

    def test_lista_og_porten(self):
        self._skjul(self.club)
        d = {s['navn']: s['skjult'] for s in self.leder.get('/park/api/steder/').json()['data']}
        self.assertEqual(d, {'Parkscene': False, 'Club': True})
        self.assertEqual(self.les.get('/park/api/steder/').status_code, 403)
        self.assertEqual(self._skjul(self.park, c=self.les).status_code, 403)
        Lokasjon.objects.filter(pk=self.park.pk).update(er_aktiv=False)
        self.assertEqual(self._skjul(self.park).status_code, 404)


class PortalinnstillingeneTests(TestCase):

    def setUp(self):
        from park.portalinnstillinger import ParkInnstillinger
        self.h = ParkInnstillinger()

    def test_fravaerende_er_behold(self):
        self.assertEqual(self.h.valider({}), {})

    def test_bryteren_av_og_paa(self):
        self.h.lagre(self.h.valider({'park_ko_posisjon_sendt': '1'}))
        self.assertFalse(services.ko_posisjon_paa())
        self.h.lagre(self.h.valider({'park_ko_posisjon_sendt': '1', 'park_ko_posisjon': '1'}))
        self.assertTrue(services.ko_posisjon_paa())

    def test_angrefristen(self):
        from django.core.exceptions import ValidationError
        self.h.lagre(self.h.valider({'park_angrefrist': '10'}))
        self.assertEqual(services.angrefrist_min(), 10)
        for feil in ('0', '31', 'x', ''):
            with self.assertRaises(ValidationError, msg=feil):
                self.h.valider({'park_angrefrist': feil})

    def test_registrert_og_malen_tegnes(self):
        from django.template.loader import render_to_string
        from core.portalinnstillinger import all_handlers
        self.assertIn('park', [h.slug for h in all_handlers()])
        html = render_to_string(self.h.mal, self.h.kontekst())
        self.assertIn('name="park_angrefrist"', html)
        self.assertIn('name="park_ko_posisjon_sendt"', html)
        self.assertIn('checked', html, 'bryteren er på uten rad')


class KommandoenTests(_Grunnlag):

    def test_lager_lenke_og_viser_tokenet_en_gang(self):
        ut = StringIO()
        call_command('park_lenke', lag='Bliksund', fra='2026-10-01T08:00', til='2026-10-04T08:00', stdout=ut)
        token = re.search(r'/park/r/#(\S+)', ut.getvalue()).group(1)
        lenke = Parklenke.objects.get(navn='Bliksund')
        self.assertEqual(lenke.hemmelighet_hash, services.hash_token(token))
        ut = StringIO()
        call_command('park_lenke', list=True, stdout=ut)
        self.assertNotIn(token, ut.getvalue())


# ── Rammeverket ──────────────────────────────────────────────────────────────

def _uten_kommentarer(kilde: str) -> str:
    """Kilden uten kommentarer og docstrings — en regel som leser sin egen
    prosa måler at noen har skrevet om begrunnelsen (CLAUDE.md)."""
    tre = ast.parse(kilde)
    for node in ast.walk(tre):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(getattr(node.body[0], 'value', None), ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tre)


class RuteneTests(TestCase):

    def _ruter(self):
        from patients.tests_modul_dekorator import _ruter_under
        return _ruter_under('park/')

    def test_api_uten_innlogging_bak_lenkeporten(self):
        funn = [m for n, cb, m in self._ruter() if m.startswith('park/r/api/')
                and not getattr(cb, '_park_lenke_kreves', False)]
        self.assertEqual(funn, [])

    def test_resten_er_modulgatet(self):
        funn = []
        for navn, cb, m in self._ruter():
            if m.startswith('park/r/'):
                continue
            krav = getattr(cb, '_modul_kreves', None)
            if not krav or krav[0] != 'park':
                funn.append(m)
        self.assertEqual(funn, [])

    def test_testen_finner_rutene(self):
        self.assertGreaterEqual(len([m for _, _, m in self._ruter() if m.startswith('park/r/api/')]), 4)

    def test_siden_uten_innlogging_leser_aldri_request_user(self):
        kilde = (Path(settings.BASE_DIR) / 'park' / 'views_lag.py').read_text(encoding='utf-8')
        self.assertNotIn('.user', _uten_kommentarer(kilde))

    def test_ingen_annen_modul_importerer_park(self):
        """Park er øverst for sine kanter: den leser `vaktliste` og `oppdrag`,
        og KO melder seg inn i `core` — ingen av dem kjenner park."""
        from core.tests_avhengighetsretning import MODULAPPER
        funn = []
        for app in sorted(MODULAPPER - {'park'}) + ['core', 'accounts', 'audit']:
            for sti in (Path(settings.BASE_DIR) / app).rglob('*.py'):
                if 'tests' in sti.name or 'migrations' in sti.parts:
                    continue
                for node in ast.walk(ast.parse(sti.read_text(encoding='utf-8'))):
                    moduler = []
                    if isinstance(node, ast.Import):
                        moduler = [a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        moduler = [node.module]
                    for m in moduler:
                        if m.split('.')[0] == 'park' and str(sti).replace(str(settings.BASE_DIR), '') != '/core/modules.py':
                            funn.append(f'{sti.name}: {m}')
        self.assertEqual(funn, [])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RutingflaggetIVaktlistaTests(_Grunnlag):
    """Knappen «Park» i gruppeoppsettet går gjennom vaktlistas PUT — oppsett,
    altså `skriv_leder` som resten av gruppa."""

    def _put(self, bruker, verdi):
        import json
        c = Client()
        c.force_login(bruker)
        return c.put(f'/vaktliste/api/grupper/{gruppe(SAMLEPLASS).pk}/',
                     data=json.dumps({'registrerer_i_park': verdi}),
                     content_type='application/json')

    def _vaktliste(self, navn, nivaa):
        b = _bruker(navn)
        ModulTilgang.objects.create(bruker=b, modul_slug='vaktliste', nivaa=nivaa)
        return b

    def test_leder_snur_flagget_og_lagnedtrekket_foelger(self):
        self.assertEqual(self._put(self._vaktliste('vl', 'skriv_leder'), True).status_code, 200)
        self.assertIn(self.samleplass, services.lagene())
        self.assertEqual(self._put(self._vaktliste('vl2', 'skriv_leder'), 'ja').status_code, 200)
        self.assertNotIn(self.samleplass, services.lagene(), 'bare literal true slår på')

    def test_skriv_full_faar_ikke(self):
        self.assertEqual(self._put(self._vaktliste('vf', 'skriv_full'), True).status_code, 403)
        self.assertNotIn(self.samleplass, services.lagene())
