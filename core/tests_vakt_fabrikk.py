"""`core.vakt.opprett_vakt` — den ene fabrikken for `Vakt`-rader (26. sep. 2026).

Tre steder laget vakter med hver sin `exists()` foran `create()`. En slik
sjekk er et kappløp, og den andre av to samtidige innsendinger fikk 500 fra
unikhetskravet. Testene tvinger fram kappløpet ved å la sjekken si «ledig»
og krever at svaret likevel er 400 — og at ingenting er halvveis gjort.
"""
import ast
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.db import transaction
from django.db.models.query import QuerySet
from django.test import Client, SimpleTestCase, TestCase, override_settings

from accounts.models import CustomUser
from core.models import AppSetting, Vakt
from core.vakt import VaktnavnOpptatt, opprett_vakt, vakt_for_year
from django.utils import timezone


class FabrikkenTests(TestCase):

    def test_tomt_navn(self):
        with self.assertRaises(ValueError):
            opprett_vakt('  ', year=2030, startet=timezone.now())

    def test_opptatt_navn_etterlater_transaksjonen_brukbar(self):
        """Savepointet: en kaller inne i en større transaksjon skal kunne
        fortsette etter nei — ellers er neste spørring en `TransactionManagementError`."""
        opprett_vakt('Sommer', year=2030, startet=timezone.now())
        with transaction.atomic():
            with self.assertRaises(VaktnavnOpptatt) as feil:
                opprett_vakt('Sommer', year=2030, startet=timezone.now())
            self.assertEqual(Vakt.objects.filter(navn='Sommer').count(), 1)
        self.assertIn('finnes allerede', str(feil.exception))

    def test_vakt_for_year_taaler_at_en_annen_rakk_det(self):
        def rakk_det(navn, **kw):
            Vakt.objects.create(navn=navn, **kw)
            raise VaktnavnOpptatt('tatt')
        with patch('core.vakt.opprett_vakt', side_effect=rakk_det):
            vakt = vakt_for_year(2031)
        self.assertEqual((vakt.navn, vakt.year), ('2031', 2031))

    def test_vakt_for_year_sier_fra_naar_navnet_er_et_annet_aars(self):
        Vakt.objects.create(navn='2032', year=2029, startet=timezone.now())
        with self.assertRaises(VaktnavnOpptatt):
            vakt_for_year(2032)


def _sjekken_sier_ledig():
    """`exists()` svarer «ledig» — som når en annen innsending ennå ikke har
    committet. Da er det `opprett_vakt` alene som må stoppe duplikatet."""
    return patch.object(QuerySet, 'exists', return_value=False)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class GjennomEndepunkteneTests(TestCase):

    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        self.vakt = sett_aktiv_vakt(2026)
        self.admin = CustomUser.objects.create_user(
            username='fabrikk_adm', password='x', role='admin', must_change_password=False)
        self.c = Client()
        self.c.force_login(self.admin)
        Vakt.objects.create(navn='Tatt', year=2026, startet=timezone.now())

    def _mappe(self):
        mappe = tempfile.TemporaryDirectory()
        self.addCleanup(mappe.cleanup)
        return mappe.name

    def _post(self, url, **kropp):
        return self.c.post(url, data=json.dumps(kropp), content_type='application/json')

    def test_ny_vaktliste_med_tatt_navn_er_400(self):
        res = self._post('/vaktliste/api/vaktlister/', navn='Tatt')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('finnes allerede', res.json()['message'])

    def test_feil_i_kopieringen_etterlater_ingen_vakt(self):
        from vaktliste.models import Vaktliste
        kilde = Vaktliste.objects.create(vakt=self.vakt)
        with patch('vaktliste.services.kopier_oppsett', side_effect=RuntimeError('midt i')):
            with self.assertRaises(RuntimeError):
                self._post('/vaktliste/api/vaktlister/', navn='Høst', kopier_fra=kilde.pk)
        self.assertFalse(Vakt.objects.filter(navn='Høst').exists(),
                         'vakta skal rulles tilbake med kopien')

    def test_avslutt_vakt_i_kappløp_sletter_ingenting(self):
        from patients.models import Patient
        Patient.objects.create(pasientnummer=1, vakt=self.vakt)
        # `/portal-admin/vakt/avslutt/` siden 28. sep. 2026 — et skjema som
        # videresender, så feilen står i meldingene.
        with _sjekken_sier_ledig(), patch.dict(os.environ, {'BACKUP_DIR': self._mappe()}):
            res = self.c.post('/portal-admin/vakt/avslutt/',
                              {'bekreft': 'ja', 'ny_vakt_navn': 'Tatt'}, follow=True)
        self.assertIn('finnes allerede', ' '.join(str(m) for m in res.context['messages']))
        self.assertTrue(Patient.objects.filter(vakt=self.vakt).exists(), 'ingen pasienter slettet')
        self.vakt.refresh_from_db()
        self.assertTrue(self.vakt.er_aktiv)
        self.assertEqual(int(AppSetting.get('aktiv_vakt_id')), self.vakt.pk)


class IngenAndreLagerVakterTests(SimpleTestCase):
    """Regelen, lest av koden: `Vakt.objects.create` bare i `core/vakt.py`."""

    def test_bare_fabrikken(self):
        rot = Path(settings.BASE_DIR)
        funn = []
        for app in ('accounts', 'audit', 'backlog', 'core', 'ko', 'oppdrag', 'patients',
                    'statistikk', 'vaktliste'):
            for fil in (rot / app).rglob('*.py'):
                if 'migrations' in fil.parts or fil.name.startswith('test') or fil.name == 'vakt.py':
                    continue
                for node in ast.walk(ast.parse(fil.read_text(encoding='utf-8'))):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr in ('create', 'get_or_create', 'bulk_create')
                            and isinstance(node.func.value, ast.Attribute)
                            and node.func.value.attr == 'objects'
                            and isinstance(node.func.value.value, ast.Name)
                            and node.func.value.value.id == 'Vakt'):
                        funn.append(f'{fil.relative_to(rot)}:{node.lineno}')
        self.assertEqual(funn, [], 'Lag vakter med core.vakt.opprett_vakt')
