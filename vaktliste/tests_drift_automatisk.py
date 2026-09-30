"""Pulje 2 (30. sep. 2026): vaktlista settes i drift av seg selv ved vaktas start.

Avgjort 15. sep. (`docs/FORSLAG_VAKTLISTE_UTBEDRINGER.md` §6): **automatisk, med
overstyring beholdt**. Kantene 30. sep.: klokka åpner, den stenger aldri; den som
møter tidlig bruker knappen.

Tjenestelaget er det tunge laget her (`CLAUDE.md`, «Mutasjonstesting»): en feil
i klokka legger seg i data og oppdages av ingen før innsjekken er stengt ved
vaktstart — eller en gammel liste åpner seg selv. Hver regel i
`services.skal_settes_i_drift()` har sin test, og kallstedene prøves gjennom de
ekte inngangene (viewene og middlewaren), ikke bare gjennom funksjonen.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from audit.models import AuditLog
from audit.utils import clear_current_request, get_current_request, set_current_request
from core.models import AppSetting

from . import choices, fil, services
from .models import Utsending, Vaktliste, Vaktpost
from .tests_tilgang import TilgangsBasis


def _liste(start_om, slutt_om=8, *, navn='Autovakta'):
    """En liste laget *nå*, med start `start_om` timer fram (negativt: passert)."""
    naa = timezone.now()
    return services.opprett_planlagt_vakt(
        navn, startet=naa + timedelta(hours=start_om),
        planlagt_slutt=(naa + timedelta(hours=slutt_om)) if slutt_om is not None else None)


def _laget_for(vl, timer):
    """Flytt `created_at` bakover, så en liste med passert start ser ut som om den
    ble laget før starten. `update()`, fordi feltet er `auto_now_add`."""
    Vaktliste.objects.filter(pk=vl.pk).update(
        created_at=vl.vakt.startet - timedelta(hours=timer))
    vl.refresh_from_db()
    return vl


class RegleneTests(TestCase):
    """`skal_settes_i_drift()` og `sett_i_drift_ved_start()` — én regel om gangen."""

    def setUp(self):
        self.vl = _liste(1, 9)
        self.start = self.vl.vakt.startet

    def _sett(self, naa):
        return services.sett_i_drift_ved_start(self.vl, naa)

    def test_settes_i_drift_ved_start(self):
        naa = self.start + timedelta(minutes=1)
        self.assertTrue(self._sett(naa))
        self.vl.refresh_from_db()
        self.assertEqual(choices.DRIFT, self.vl.status)
        self.assertTrue(self.vl.drift_automatisk)
        self.assertIsNone(self.vl.satt_i_drift_av)
        self.assertEqual(naa, self.vl.satt_i_drift_at)

    def test_ikke_foer_start(self):
        self.assertFalse(self._sett(self.start - timedelta(seconds=1)))
        self.assertTrue(self._sett(self.start), 'akkurat ved start skal den åpne')

    def test_ikke_ved_eller_etter_planlagt_slutt(self):
        slutt = self.vl.planlagt_slutt
        self.assertFalse(self._sett(slutt))
        self.assertTrue(self._sett(slutt - timedelta(seconds=1)))

    def test_uten_slutt_bare_det_forste_dognet(self):
        vl = _liste(1, None, navn='Uten slutt')
        start = vl.vakt.startet
        self.assertFalse(services.skal_settes_i_drift(vl, start + services.AUTODRIFT_UTEN_SLUTT))
        self.assertTrue(services.skal_settes_i_drift(
            vl, start + services.AUTODRIFT_UTEN_SLUTT - timedelta(seconds=1)))

    def test_start_passert_da_lista_ble_laget(self):
        """«Ny vaktliste» uten start gir start = nå. Uten regelen gikk lista i
        drift idet den ble laget — og gamle lister åpnet seg ved deploy."""
        vl = _liste(-1, 8, navn='Passert')
        self.assertFalse(services.sett_i_drift_ved_start(vl, timezone.now()))
        self.assertEqual(choices.PLANLEGGING, Vaktliste.objects.get(pk=vl.pk).status)

    def test_laget_akkurat_ved_start_er_ikke_foer(self):
        Vaktliste.objects.filter(pk=self.vl.pk).update(created_at=self.start)
        self.vl.refresh_from_db()
        self.assertFalse(self._sett(self.start + timedelta(minutes=1)))

    def test_bare_en_gang(self):
        """Tok noen lista *ut* av drift, var det et valg."""
        self._sett(self.start)
        Vaktliste.objects.filter(pk=self.vl.pk).update(status=choices.PLANLEGGING)
        self.vl.refresh_from_db()
        self.assertFalse(self._sett(self.start + timedelta(minutes=5)))

    def test_arkivert_aapnes_ikke(self):
        Vaktliste.objects.filter(pk=self.vl.pk).update(arkivert_at=timezone.now())
        self.vl.refresh_from_db()
        self.assertFalse(self._sett(self.start))

    def test_avsluttet_vakt_aapnes_ikke(self):
        vakt = self.vl.vakt
        vakt.avsluttet = self.start
        vakt.save(update_fields=['avsluttet'])
        self.assertFalse(self._sett(self.start + timedelta(minutes=1)))

    def test_alt_i_drift_rores_ikke(self):
        Vaktliste.objects.filter(pk=self.vl.pk).update(status=choices.DRIFT)
        self.vl.refresh_from_db()
        self.assertFalse(self._sett(self.start))
        self.vl.refresh_from_db()
        self.assertFalse(self.vl.drift_automatisk)

    def test_forfalte_tar_bare_dem_som_skal(self):
        passert = _liste(-1, 8, navn='Passert ved laging')
        framtid = _liste(5, 9, navn='Senere')
        satt = services.sett_forfalte_i_drift(self.start + timedelta(minutes=1))
        self.assertEqual([self.vl.pk], [v.pk for v in satt])
        for vl in (passert, framtid):
            self.assertEqual(choices.PLANLEGGING, Vaktliste.objects.get(pk=vl.pk).status)

    def test_autodrift_tidspunkt(self):
        """Det knappen sier: «settes i drift av seg selv …» — bare når det stemmer."""
        self.assertEqual(self.start, services.autodrift_tidspunkt(self.vl))
        self.assertIsNone(services.autodrift_tidspunkt(_liste(-1, 8, navn='Ingen auto')))


class AuditOgKnappTests(TilgangsBasis):

    def setUp(self):
        super().setUp()
        self.auto = _liste(1, 9)

    def tearDown(self):
        clear_current_request()
        super().tearDown()

    def test_auditraden_staar_ikke_paa_den_som_aapnet_siden(self):
        """Klokka kan gå inne i et view. Da skal raden ikke stå på den som
        tilfeldigvis gjorde forespørselen."""
        forespoersel = SimpleNamespace(user=self.leser, META={'REMOTE_ADDR': '10.0.0.9'})
        set_current_request(forespoersel)
        services.sett_i_drift_ved_start(self.auto, self.auto.vakt.startet)
        rader = AuditLog.objects.filter(record_id=self.auto.pk, field_name='status')
        self.assertTrue(rader.exists(), 'endringen skal fortsatt logges')
        self.assertFalse(rader.filter(user__isnull=False).exists())
        self.assertIs(forespoersel, get_current_request(), 'requesten settes tilbake')

    def test_knappen_er_en_person_ikke_klokka(self):
        services.sett_i_drift_ved_start(self.auto, self.auto.vakt.startet)
        self.c_vl.post(f'/vaktliste/api/vaktlister/{self.auto.pk}/drift/stopp/')
        self.c_vl.post(f'/vaktliste/api/vaktlister/{self.auto.pk}/drift/start/')
        self.auto.refresh_from_db()
        self.assertFalse(self.auto.drift_automatisk)
        self.assertEqual(self.vaktleder, self.auto.satt_i_drift_av)

    def test_knappen_foer_start_hindrer_klokka_etterpaa(self):
        """Åpnet og stengt før start: klokka skal ikke åpne igjen."""
        self.c_vl.post(f'/vaktliste/api/vaktlister/{self.auto.pk}/drift/start/')
        self.c_vl.post(f'/vaktliste/api/vaktlister/{self.auto.pk}/drift/stopp/')
        self.assertEqual([], services.sett_forfalte_i_drift(
            self.auto.vakt.startet + timedelta(minutes=1)))


class FilaVedAutomatiskDriftTests(TestCase):
    """Utløseren forsvant ikke med knappen: fila sendes som før."""

    def setUp(self):
        AppSetting.set(fil.MOTTAKERE_NOKKEL, 'vaktleder@example.org')
        self.vl = _liste(1, 9)

    def _driftfiler(self):
        return Utsending.objects.filter(vaktliste=self.vl, utloest=Utsending.DRIFT).count()

    def test_sendes_en_gang(self):
        start = self.vl.vakt.startet
        services.sett_i_drift_ved_start(self.vl, start)
        services.sett_i_drift_ved_start(self.vl, start + timedelta(minutes=1))
        services.sett_forfalte_i_drift(start + timedelta(minutes=2))
        self.assertEqual(1, self._driftfiler())

    def test_ikke_naar_admin_har_slaatt_det_av(self):
        AppSetting.set(fil.VED_DRIFT_NOKKEL, '0')
        services.sett_i_drift_ved_start(self.vl, self.vl.vakt.startet)
        self.assertEqual(0, self._driftfiler())


class KallstedeneTests(TilgangsBasis):
    """Gjennom de ekte inngangene. Kaller testen bare funksjonen, kan et kallsted
    forsvinne uten at noe blir rødt — regel 3 i `CLAUDE.md`."""

    def setUp(self):
        super().setUp()
        # Vakta i grunnoppsettet startet «nå» og ble laget etterpå — gjør den
        # til en som ble planlagt i forveien og har nådd starten.
        vakt = self.vl.vakt
        vakt.startet = timezone.now() - timedelta(minutes=1)
        vakt.save(update_fields=['startet'])
        self.vl.planlagt_slutt = timezone.now() + timedelta(hours=8)
        self.vl.save(update_fields=['planlagt_slutt'])
        _laget_for(self.vl, 24)

    def _status(self):
        return Vaktliste.objects.get(pk=self.vl.pk).status

    def test_forste_stempel_etter_start_aapner_innsjekken(self):
        vp = Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd,
            fra_tid=self.na, til_tid=self.na + timedelta(hours=8))
        res = self.c_vl.post(f'/vaktliste/api/vaktposter/{vp.pk}/stempling/mott/')
        self.assertEqual(200, res.status_code, res.content)
        self.assertEqual(choices.DRIFT, self._status())

    def test_lista_aapnes_naar_den_leses(self):
        res = self.c_leser.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/')
        self.assertEqual(200, res.status_code)
        self.assertTrue(res.json()['data']['vaktliste']['i_drift'])
        self.assertTrue(res.json()['data']['vaktliste']['drift_automatisk'])

    def test_velgeren_aapner_den(self):
        res = self.c_leser.get('/vaktliste/api/vaktlister/')
        rad = next(r for r in res.json()['data'] if r['id'] == self.vl.pk)
        self.assertTrue(rad['i_drift'])

    def test_middlewarens_klokke(self):
        from . import middleware
        with patch.object(fil, 'send_planlagte', return_value=[]):
            middleware._kjor()
        self.assertEqual(choices.DRIFT, self._status())

    def test_middlewarens_klokke_overlever_en_feil_i_drift(self):
        """En feil i den ene skal ikke stoppe den andre."""
        from . import middleware
        with patch.object(services, 'sett_forfalte_i_drift', side_effect=RuntimeError('boom')), \
                patch.object(fil, 'send_planlagte', return_value=[]) as sp:
            middleware._kjor()
        sp.assert_called_once()


class DriftforklaringTests(TestCase):
    """Teksten ved knappen: knappen er overstyringen, klokka er normalen."""

    def setUp(self):
        from patients.js_test_utils import VAKTLISTE_JS, build_harness, node_available
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(
            ((VAKTLISTE_JS, ('driftforklaring', '_dag', '_kl', '_d')),))

    def _tekst(self, vl, i_drift):
        import json
        from patients.js_test_utils import run_node
        ut = run_node(self.harness, f"""
            globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];
            globalThis.MND = ['jan','feb','mar','apr','mai','jun','jul','aug','sep','okt','nov','des'];
            console.log(driftforklaring({json.dumps(vl)}, {json.dumps(i_drift)}));
        """)
        return ut.splitlines()[0]

    def test_sier_naar_klokka_aapner(self):
        tekst = self._tekst({'autodrift_at': '2026-10-02T15:00:00+02:00'}, False)
        self.assertIn('av seg selv', tekst)
        self.assertIn('15:00', tekst)

    def test_uten_klokke_er_knappen_veien(self):
        self.assertNotIn('av seg selv', self._tekst({'autodrift_at': None}, False))

    def test_i_drift_sier_om_det_var_klokka(self):
        self.assertIn('automatisk', self._tekst({'drift_automatisk': True}, True))
        self.assertNotIn('automatisk', self._tekst({'drift_automatisk': False}, True))
