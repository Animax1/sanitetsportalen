"""Endringsnummeret for tavla (24. sep. 2026): hva som øker tallet, hvem som
får spørre, og at skrivinger utenom signalene er vurdert.

André: to på tavla fordeler arbeidet muntlig, og 15 sekunder var lenge å
vente på at kollegaens flytting viste seg. Et tall som ikke øker, er et bilde
som står feil til sikkerhetsnettet slår inn — derfor prøves hver kilde.
"""
from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from core import endringer
from core.models import AppSetting
from ko import signals as ko_signals
from ko import tavle
from ko.endringer import TAVLE
from vaktliste.models import Pause

from .tests_tavle import PorteneTests, _Grunnlag


class _Teller(_Grunnlag):

    def setUp(self):
        super().setUp()
        cache.clear()

    def _endrer(self, fn):
        foer = endringer.versjon(TAVLE)
        with self.captureOnCommitCallbacks(execute=True):
            fn()
        return endringer.versjon(TAVLE) != foer


class HvaSomOekerTalletTests(_Teller):

    def test_en_flytting_paa_tavla(self):
        self.assertTrue(self._endrer(lambda: self._plasser(self.lag1, self.park)))

    def test_en_pause_i_vaktlista(self):
        naa = timezone.now()
        self.assertTrue(self._endrer(lambda: Pause.objects.create(
            ressurs=self.lag1, fra=naa + timedelta(minutes=5), til=naa + timedelta(minutes=35))))

    def test_en_plan_og_sletting_av_den(self):
        naa = timezone.now()
        q = tavle.planlegg_pause(self.vakt, self.lag1, bruker=self.operator,
                                 fra=naa + timedelta(minutes=5), til=naa + timedelta(minutes=35))
        self.assertTrue(self._endrer(lambda: tavle.slett_pause(q)))

    def test_bare_tavlas_innstillinger_ikke_pasienttelleren(self):
        self.assertTrue(self._endrer(lambda: AppSetting.set(tavle.ANDEL_BAK_NOKKEL, '10')))
        self.assertFalse(self._endrer(lambda: AppSetting.set('next_patient_nr_vakt_1', '42')),
                         'hver pasientregistrering ville fått alle fanene til å hente tavla')

    def test_ikke_under_loaddata(self):
        foer = endringer.versjon(TAVLE)
        with self.captureOnCommitCallbacks(execute=True):
            ko_signals.tavla_endret(sender=Pause, instance=None, raw=True)
        self.assertEqual(endringer.versjon(TAVLE), foer)


class TavlasModellerErKobletTests(SimpleTestCase):
    """Hver modell tavla leser, skal øke tallet ved lagring — og ved sletting
    der raden kan forsvinne. Fjernes en mottaker, blir dette rødt."""

    LAGRING = ('ko.Tavleplassering', 'ko.PlanlagtPause', 'ko.Programpost', 'ko.Programbehov',
               'ko.Hendelse', 'ko.HendelseLag', 'vaktliste.Pause', 'vaktliste.Vaktpost',
               'vaktliste.Ressurs', 'oppdrag.Oppdrag', 'oppdrag.Statusmelding',
               'oppdrag.Oppdragsenhet', 'oppdrag.Enhet', 'oppdrag.Lokasjon')
    #: Enhet og Lokasjon slettes ikke i drift — de deaktiveres (`er_aktiv`).
    SLETTING = tuple(m for m in LAGRING if m not in ('oppdrag.Enhet', 'oppdrag.Lokasjon'))

    def _koblet(self, signal, etikett):
        """Er `tavla_endret` blant mottakerne? Django 5 gir `(synkrone,
        asynkrone)`; mottakeren vår er synkron."""
        from django.apps import apps
        synkrone, _asynkrone = signal._live_receivers(apps.get_model(etikett))
        return any(r is ko_signals.tavla_endret for r in synkrone)

    def test_lagring_og_sletting(self):
        mangler = [f'post_save {m}' for m in self.LAGRING if not self._koblet(post_save, m)]
        mangler += [f'post_delete {m}' for m in self.SLETTING if not self._koblet(post_delete, m)]
        self.assertEqual(mangler, [])


class TavleEndringerFangesTests(SimpleTestCase):
    """**`.update()` og `bulk_*` sender ingen signaler.** En slik skriving på
    en modell tavla leser, øker ikke tallet — med mindre den skjer i samme
    transaksjon som noe som gjør det. Hver av dem skal være vurdert og stå
    her med begrunnelse. `.delete()` på et queryset sender `post_delete` per
    rad, og er ikke med."""

    SPORET = {m.split('.')[1] for m in TavlasModellerErKobletTests.LAGRING}
    UTENOM = {'update', 'bulk_create', 'bulk_update'}

    VURDERT = {
        'ko/tavle.py: Tavleplassering.update': 'avslutt_for_hendelse kalles fra services.sett_lag, '
                                               'som lagrer HendelseLag i samme transaksjon',
        'oppdrag/services.py: Statusmelding.update': '_slett_meldinger kobler fra korrigerer rett før '
                                                     'meldingene og oppdraget slettes (post_delete)',
    }

    def test_hver_skriving_utenom_signalene_er_vurdert(self):
        funn = set()
        for app in ('ko', 'vaktliste', 'oppdrag', 'core', 'patients', 'statistikk', 'backlog',
                    'accounts', 'audit'):
            for fil in sorted((Path(settings.BASE_DIR) / app).rglob('*.py')):
                if 'migrations' in fil.parts or fil.name.startswith(('tests', 'test_')):
                    continue
                for n in ast.walk(ast.parse(fil.read_text(encoding='utf-8'))):
                    if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                            and n.func.attr in self.UTENOM):
                        continue
                    k, modell = n.func.value, None
                    while isinstance(k, (ast.Call, ast.Attribute)):
                        if isinstance(k, ast.Attribute) and k.attr == 'objects' and isinstance(k.value, ast.Name):
                            modell = k.value.id
                            break
                        k = k.func if isinstance(k, ast.Call) else k.value
                    if modell in self.SPORET:
                        rel = fil.relative_to(settings.BASE_DIR).as_posix()
                        funn.add(f'{rel}: {modell}.{n.func.attr}')
        self.assertEqual(sorted(funn - set(self.VURDERT)), [],
                         'ny skriving utenom signalene — øker den tavlas tall? Vurder og før den inn')
        self.assertEqual(sorted(set(self.VURDERT) - funn), [], 'står i VURDERT, men finnes ikke lenger')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PortenOgSvaretTests(PorteneTests):

    def test_tavlas_tall_krever_tavlas_tilgang(self):
        url = '/api/endringer/?omrader=tavle'
        self.assertIn(TAVLE, self._klient('les').get(url).json())
        self.assertNotIn(TAVLE, self._klient('les', vaktliste=None).get(url).json(),
                         'uten vaktlista, ingen tavle — og ikke noe tall')
        self.assertNotIn(TAVLE, self._klient(None).get(url).json())

    def test_svaret_sier_hvem_som_satte_plasseringen(self):
        self._plasser(self.lag1, self.park)
        (p,) = [p for p in tavle.tavle_data(self.vakt)['plasseringer'] if not p['til']]
        self.assertEqual(p['av_navn'], 'ko1')
