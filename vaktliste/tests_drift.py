# -*- coding: utf-8 -*-
"""Fase 4 — drift: innsjekk-porten, stemplene og «Tilstede nå».

**Drift betyr én ting: innsjekk er åpen** (§5). Ikke en livssyklus, ikke en
låsing. Lista kan fortsatt endres — folk uteblir og bytter, og en liste som
låser seg idet vakta starter er en liste som forlates til fordel for et ark.

Tre ting bæres av testene her, og de er alle beslutninger noen kan komme til
å ville løsne på:

1. **Korps-føreren stempler ikke** (avklaring 11.3). Hun setter opp sine egne
   folk, men «Tilstede nå» er brannsikkerhet på et sted med overnatting, og
   det tallet skal ha én ansvarlig — ikke ett per korps.
2. **Innsjekk er stengt utenfor drift.** Et møtt-stempel før vakta finnes
   ikke, og ett etter at innsjekken er stengt er en rad ingen har tatt
   ansvar for.
3. **Stemplene har forutsetninger.** «Av vakt» uten «møtt» gir en rad som
   sier at noen gikk av en vakt hun aldri kom til — og `er_tilstede` leser
   nettopp de to feltene sammen.
"""
from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from . import choices, services
from .models import Vaktpost
from .tests_tilgang import TilgangsBasis


class DriftportenTests(TilgangsBasis):
    """Døra inn til innsjekk, og hvem som får åpne den."""

    def _sett(self, klient, tilstand):
        return klient.post(
            f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/{tilstand}/')

    def test_vaktlederen_apner_og_stenger(self):
        res = self._sett(self.c_vl, 'start')
        self.assertEqual(200, res.status_code, res.content)
        self.assertTrue(res.json()['data']['i_drift'])
        self.vl.refresh_from_db()
        self.assertEqual(choices.DRIFT, self.vl.status)

        res = self._sett(self.c_vl, 'stopp')
        self.assertEqual(200, res.status_code)
        self.assertFalse(res.json()['data']['i_drift'])

    def test_lederen_og_admin_ogsaa(self):
        """Stigen er ordnet — `skriv_leder` gjør alt bemanneren gjør."""
        for navn, c in (('leder', self.c_leder), ('admin', self.c_adm)):
            with self.subTest(konto=navn):
                self.assertEqual(200, self._sett(c, 'start').status_code)
                self._sett(c, 'stopp')

    def test_korpsforeren_apner_ikke_innsjekken(self):
        """Avklaring 11.3. Hun fører sitt korps; innsjekken er ikke hennes."""
        self.assertEqual(403, self._sett(self.c_kb, 'start').status_code)
        self.vl.refresh_from_db()
        self.assertEqual(choices.PLANLEGGING, self.vl.status)

    def test_leseren_apner_ikke(self):
        self.assertEqual(403, self._sett(self.c_leser, 'start').status_code)

    def test_ukjent_tilstand_er_ikke_en_veksling(self):
        """Et veksle-endepunkt ville gitt et kappløp når to trykk kommer
        tett. Retningen står i URL-en, og bare de to finnes."""
        self.assertEqual(404, self._sett(self.c_vl, 'veksle').status_code)
        self.assertEqual(404, self._sett(self.c_vl, 'pause').status_code)

    def test_tidspunktet_settes_ved_apning(self):
        self._sett(self.c_vl, 'start')
        self.vl.refresh_from_db()
        self.assertIsNotNone(self.vl.satt_i_drift_at)
        self.assertEqual(self.vaktleder, self.vl.satt_i_drift_av)

    def test_stenging_beholder_tidspunktet(self):
        """«I drift siden 08:04» skal fortsatt kunne leses etterpå."""
        self._sett(self.c_vl, 'start')
        self.vl.refresh_from_db()
        apnet = self.vl.satt_i_drift_at
        self._sett(self.c_vl, 'stopp')
        self.vl.refresh_from_db()
        self.assertEqual(apnet, self.vl.satt_i_drift_at)

    def test_ut_av_drift_rorer_ingen_stempler(self):
        """Det er en dør, ikke en sletting. En pause i arrangementet eller et
        feilklikk skal kunne rettes uten at oppmøtet forsvinner."""
        self._sett(self.c_vl, 'start')
        vp = self._vaktpost()
        self.c_vl.post(f'/vaktliste/api/vaktposter/{vp.pk}/stempling/mott/')
        self._sett(self.c_vl, 'stopp')
        vp.refresh_from_db()
        self.assertIsNotNone(vp.mott_at)

    def _vaktpost(self):
        return Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd,
            fra_tid=self.na, til_tid=self.na + timedelta(hours=8))


class StemplingTests(TilgangsBasis):
    """Møtt, av vakt, og angring av begge."""

    def setUp(self):
        super().setUp()
        self.vl.status = choices.DRIFT
        self.vl.save(update_fields=['status'])
        self.vp = Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd,
            fra_tid=self.na, til_tid=self.na + timedelta(hours=8))
        self.ledig = Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=None,
            fra_tid=self.na, til_tid=self.na + timedelta(hours=8))

    def _stempl(self, handling, klient=None, vaktpost=None):
        vp = vaktpost or self.vp
        return (klient or self.c_vl).post(
            f'/vaktliste/api/vaktposter/{vp.pk}/stempling/{handling}/')

    # ── Den vanlige veien ────────────────────────────────────────────────
    def test_mott_setter_tidspunktet(self):
        res = self._stempl('mott')
        self.assertEqual(200, res.status_code, res.content)
        self.vp.refresh_from_db()
        self.assertIsNotNone(self.vp.mott_at)
        self.assertTrue(res.json()['data']['tilstede'])

    def test_av_vakt_etter_mott(self):
        self._stempl('mott')
        res = self._stempl('av_vakt')
        self.assertEqual(200, res.status_code, res.content)
        self.vp.refresh_from_db()
        self.assertIsNotNone(self.vp.av_vakt_at)
        self.assertFalse(self.vp.er_tilstede, 'gått av vakt er ikke tilstede')

    def test_dobbelt_mott_flytter_ikke_tidspunktet(self):
        """To trykk på samme knapp skal gi samme rad, ikke en rød boks. Men
        det første tidspunktet er det som skjedde."""
        self._stempl('mott')
        self.vp.refresh_from_db()
        forste = self.vp.mott_at
        res = self._stempl('mott')
        self.assertEqual(200, res.status_code)
        self.vp.refresh_from_db()
        self.assertEqual(forste, self.vp.mott_at)

    # ── Forutsetningene ──────────────────────────────────────────────────
    def test_av_vakt_uten_mott_avvises(self):
        """En rad som sier at noen gikk av en vakt hun aldri kom til."""
        res = self._stempl('av_vakt')
        self.assertEqual(400, res.status_code)
        self.assertIn('møtt', res.json()['message'])
        self.vp.refresh_from_db()
        self.assertIsNone(self.vp.av_vakt_at)

    def test_angre_mott_mens_av_vakt_staar_avvises(self):
        """Samme ugyldige rad, andre vei inn."""
        self._stempl('mott')
        self._stempl('av_vakt')
        res = self._stempl('angre_mott')
        self.assertEqual(400, res.status_code)
        self.vp.refresh_from_db()
        self.assertIsNotNone(self.vp.mott_at)

    def test_angring_gaar_i_riktig_rekkefolge(self):
        self._stempl('mott')
        self._stempl('av_vakt')
        self.assertEqual(200, self._stempl('angre_av_vakt').status_code)
        self.assertEqual(200, self._stempl('angre_mott').status_code)
        self.vp.refresh_from_db()
        self.assertIsNone(self.vp.mott_at)
        self.assertIsNone(self.vp.av_vakt_at)

    def test_angre_noe_som_ikke_staar(self):
        self.assertEqual(400, self._stempl('angre_av_vakt').status_code)

    def test_ledig_plass_kan_ikke_stemples(self):
        """Den har ingen som kan ha møtt — og `er_tilstede` krever en person
        nettopp derfor."""
        res = self._stempl('mott', vaktpost=self.ledig)
        self.assertEqual(400, res.status_code)
        self.assertIn('ledig', res.json()['message'].lower())

    def test_ukjent_stempling(self):
        self.assertEqual(404, self._stempl('kaffepause').status_code)

    # ── Portene, og rekkefølgen på dem ───────────────────────────────────
    def test_korpsforeren_stempler_ikke_sine_egne(self):
        """Avklaring 11.3. Kari er *hennes* — hun satte henne opp — og hun
        får likevel ikke sjekke henne inn."""
        res = self._stempl('mott', klient=self.c_kb)
        self.assertEqual(403, res.status_code)
        self.vp.refresh_from_db()
        self.assertIsNone(self.vp.mott_at)

    def test_leseren_stempler_ikke(self):
        self.assertEqual(403, self._stempl('mott', klient=self.c_leser).status_code)

    def test_utenfor_drift_er_innsjekken_stengt(self):
        self.vl.status = choices.PLANLEGGING
        self.vl.save(update_fields=['status'])
        res = self._stempl('mott')
        self.assertEqual(409, res.status_code)
        self.assertIn('drift', res.json()['message'])

    def test_tilgang_svares_for_drift(self):
        """Rekkefølgen på portene er med vilje: en korps-fører som trykker
        skal få vite at hun ikke har lov, ikke at lista ikke er i drift.

        Sto sjekkene motsatt vei, ville hun fått «sett lista i drift først» —
        et råd som fører henne til en knapp hun heller ikke har.
        """
        self.vl.status = choices.PLANLEGGING
        self.vl.save(update_fields=['status'])
        self.assertEqual(403, self._stempl('mott', klient=self.c_kb).status_code)


class StemplingsreglerTests(SimpleTestCase):
    """`services.stemple()` uten en database.

    Reglene er data (`STEMPLINGER`), og de skal kunne prøves uten en rad —
    det er halve grunnen til at de ligger i services og ikke i viewet.
    """

    class FalskPost:
        def __init__(self, **felt):
            self.mannskap_id = felt.get('mannskap_id', 1)
            self.mott_at = felt.get('mott_at')
            self.av_vakt_at = felt.get('av_vakt_at')

    def test_mott_setter_tidspunktet_som_gis(self):
        na = timezone.now()
        vp = self.FalskPost()
        ok, feil = services.stemple(vp, 'mott', naa=na)
        self.assertTrue(ok, feil)
        self.assertEqual(na, vp.mott_at)

    def test_ukjent_handling_svarer_nei(self):
        ok, feil = services.stemple(self.FalskPost(), 'noe-annet')
        self.assertFalse(ok)
        self.assertIn('Ukjent', feil)

    def test_ledig_plass_svarer_nei(self):
        ok, feil = services.stemple(self.FalskPost(mannskap_id=None), 'mott')
        self.assertFalse(ok)
        self.assertIn('ledig', feil.lower())

    def test_hver_handling_har_en_nektmelding(self):
        """En regel som avviser uten å si hvorfor, er en vegg."""
        for navn, regel in services.STEMPLINGER.items():
            with self.subTest(handling=navn):
                self.assertTrue(regel['nekt'].strip(),
                                f'{navn} avviser uten forklaring')
