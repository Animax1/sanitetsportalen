"""Audit for portalens egne tabeller (14. sep. 2026).

Hullet: `AppSetting`, `ModuleSettings` og `Vakt` sto uten audit i det hele
tatt. Å slå av en modul for alle, eller flytte sesjonstimeouten, etterlot
ingen spor — mens hvert feltbytte på en pasient ble logget minutiøst.

Den vanskelige halvdelen er ikke å logge, men å la være: `AppSetting` blander
innstillinger et menneske har bestemt med tellere maskinen har talt, og
telleren skrives ved **hver** pasientregistrering.
"""
from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from audit.models import AuditLog
from core.models import AppSetting, ModuleSettings, Vakt
from core.signals import NOKLER_UTEN_AUDIT, nokkel_logges


def _rader(tabell, **filtre):
    return AuditLog.objects.filter(table_name=tabell, **filtre)


class NokkelReglenTests(TestCase):
    """Regelen alene, uten database rundt seg."""

    def test_innstillinger_logges(self):
        for key in ('session_timeout_hours', 'aktiv_vakt_id',
                    'oppdrag_lyd_aktiv', 'vaktliste.fil.mottakere'):
            self.assertTrue(nokkel_logges(key), key)

    def test_tellerne_logges_ikke(self):
        """Den avgjørende: én skriving per pasient, én per oppdrag."""
        self.assertFalse(nokkel_logges('next_patient_nr_vakt_7'))
        self.assertFalse(nokkel_logges('next_oppdrag_nr_vakt_12'))

    def test_prefiks_og_ikke_eksakt_navn(self):
        """Nøkkelen bærer vakt-ID. En eksakt liste ville sluppet gjennom hver
        nye vakt — altså virket i test og lekket i drift."""
        for pk in (1, 7, 999, 123456):
            self.assertFalse(nokkel_logges(f'next_patient_nr_vakt_{pk}'))

    def test_cron_logges_ikke(self):
        self.assertFalse(nokkel_logges('cron.purge_old_logs'))
        self.assertFalse(nokkel_logges('cron.kollaps_arkiv'))

    def test_lista_er_en_unntaksliste(self):
        """En ukjent nøkkel skal **logges**. Feiler man, skal man feile mot
        for mye logg, ikke mot et hull man oppdager om et år."""
        self.assertTrue(nokkel_logges('noe_helt_nytt_ingen_har_tenkt_paa'))
        self.assertTrue(nokkel_logges(''))

    def test_ingen_teller_er_et_prefiks_av_en_innstilling(self):
        """Sperrehake: legger noen til et kort prefiks som «next_» eller «a»,
        slår det ut innstillinger ingen mente å skjule."""
        for prefiks in NOKLER_UTEN_AUDIT:
            self.assertGreaterEqual(
                len(prefiks), 5,
                f'prefikset {prefiks!r} er så kort at det treffer bredt')


class AppSettingAuditTests(TestCase):

    def test_endring_gir_rad_med_verdier(self):
        AppSetting.set('session_timeout_hours', '8')
        _rader('patients_appsetting').delete()

        AppSetting.set('session_timeout_hours', '720')

        rad = _rader('patients_appsetting', field_name='session_timeout_hours').get()
        self.assertEqual(rad.action, 'UPDATE')
        self.assertEqual(rad.old_value, '8')
        self.assertEqual(rad.new_value, '720')

    def test_nokkelen_staar_i_field_name_ikke_record_id(self):
        """`key` er tekst-PK, `record_id` er BigInteger. Raden skal si
        *hvilken innstilling*, ikke «rad nummer hva»."""
        AppSetting.set('oppdrag_lyd_aktiv', 'false')
        rad = _rader('patients_appsetting').get()
        self.assertEqual(rad.field_name, 'oppdrag_lyd_aktiv')
        self.assertEqual(rad.record_id, 0)

    def test_opprettelse_gir_en_rad_ikke_to(self):
        """Både `pre_save` og `post_save` fyrer. Uten oppslaget mot basen i
        `pre_save` ville en ny nøkkel gitt både UPDATE og CREATE."""
        AppSetting.set('helt_ny_nokkel', 'ja')
        rader = _rader('patients_appsetting', field_name='helt_ny_nokkel')
        self.assertEqual(rader.count(), 1)
        self.assertEqual(rader.get().action, 'CREATE')

    def test_uendret_verdi_gir_ingen_rad(self):
        AppSetting.set('session_timeout_hours', '8')
        _rader('patients_appsetting').delete()
        AppSetting.set('session_timeout_hours', '8')
        self.assertEqual(_rader('patients_appsetting').count(), 0)

    def test_sletting_logges(self):
        """En slettet innstilling faller tilbake på kodens standardverdi —
        en stille oppførselsendring."""
        AppSetting.set('oppdrag_lyd_aktiv', 'false')
        _rader('patients_appsetting').delete()
        AppSetting.objects.filter(key='oppdrag_lyd_aktiv').delete()
        rad = _rader('patients_appsetting').get()
        self.assertEqual(rad.action, 'DELETE')
        self.assertEqual(rad.old_value, 'false')

    def test_telleren_gir_ingen_rader_uansett_hvor_mange_ganger(self):
        """Kjernen i unntaket. Hundre pasienter skal ikke gi hundre rader."""
        for nr in range(1, 101):
            AppSetting.set('next_patient_nr_vakt_7', str(nr))
        self.assertEqual(_rader('patients_appsetting').count(), 0)

    def test_app_label_blir_core_og_ikke_patients(self):
        """Tabellnavnet er fortsatt `patients_appsetting` (med vilje — se
        `core/models.py`), så uten `EKSPLISITT_MAPPING` ville raden stått som
        «patients». Her blir mappingen virksom for første gang."""
        AppSetting.set('session_timeout_hours', '12')
        self.assertEqual(_rader('patients_appsetting').get().app_label, 'core')


class ModuleSettingsAuditTests(TestCase):

    def test_avslaatt_modul_logges(self):
        """Blant de mest inngripende knappene i portalen: den tar modulen fra
        alle brukere på én gang, uten deploy."""
        rad_i_basen = ModuleSettings.objects.filter(slug='patients').first()
        if rad_i_basen is None:
            rad_i_basen = ModuleSettings.objects.create(slug='patients', enabled=True)
        rad_i_basen.enabled = True
        rad_i_basen.save()
        _rader('core_modulesettings').delete()

        rad_i_basen.enabled = False
        rad_i_basen.save()

        rad = _rader('core_modulesettings', field_name='enabled').get()
        self.assertEqual(rad.old_value, 'True')
        self.assertEqual(rad.new_value, 'False')

    def test_false_blir_ikke_tom_streng(self):
        """`_verdi()` kollapser kun `None`. Ble alle falsy verdier til `''`,
        ville en deaktivering aldri blitt logget riktig — den feilen kostet
        pasientmodulen akkurat det."""
        from core.signals import _verdi
        self.assertEqual(_verdi(False), 'False')
        self.assertEqual(_verdi(0), '0')
        self.assertEqual(_verdi(None), '')


class VaktAuditTests(TestCase):

    def test_opprettelse_og_avslutning_logges(self):
        vakt = Vakt.objects.create(navn='Teststevnet 2026', year=2026,
                                   startet=timezone.now(), er_aktiv=True)
        self.assertEqual(_rader('core_vakt', action='CREATE').count(), 1)

        _rader('core_vakt').delete()
        vakt.avsluttet = timezone.now()
        vakt.er_aktiv = False
        vakt.save()

        felt = set(_rader('core_vakt').values_list('field_name', flat=True))
        self.assertEqual(felt, {'avsluttet', 'er_aktiv'})
