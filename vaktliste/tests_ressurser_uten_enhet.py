"""KOs tavle: ressursene som ikke er koblet til en oppdragsenhet (pulje 6).

Lag, samleplass, KO — det som bemannes i vaktlista, men aldri stempler i
`/oppdrag/`. Tre ting bæres av testene her, samme tre som `tests_besetning.py`:
gaten er vaktlistas, svaret bærer telefon og ISSI (fra 19. sep. 2026, André:
alle ressurser skal ha «telefonnummer og ISSI» — bak et klikk), og scopet er
lista i bruk.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from accounts.models import ModulTilgang
from core.models import AppSetting
from oppdrag.models import Enhet

from . import services
from .models import Mannskap, Vaktpost
from .test_helpers import AMBULANSE, gruppe, lag_ressurs
from .tests_tilgang import TilgangsBasis


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RessurserUtenEnhetTests(TilgangsBasis):

    STI = '/vaktliste/api/ressurser/uten-enhet/'

    def setUp(self):
        super().setUp()
        AppSetting.set('aktiv_vakt_id', self.vl.vakt.pk)
        # En bil med enhet — den hører til `/oppdrag/` og skal ikke være med.
        self.enhet = Enhet.objects.create(navn='HGSD 56')
        self.bil = lag_ressurs(vaktliste=self.vl, navn='Ambulanse 1',
                               gruppe=gruppe(AMBULANSE), enhet=self.enhet)

    def _skift(self, ressurs, person, *, fra=-1, til=7, **felt):
        return Vaktpost.objects.create(
            ressurs=ressurs, mannskap=person, rolle=self.rolle,
            fra_tid=self.na + timedelta(hours=fra),
            til_tid=self.na + timedelta(hours=til), **felt)

    def test_bare_ressurser_uten_enhet(self):
        self._skift(self.res_hgsd, self.p_hgsd)
        self._skift(self.res_fri, self.p_karmoy)
        self._skift(self.bil, self.p_hgsd)
        navn = [r['navn'] for r in services.ressurser_uten_enhet()]
        self.assertIn('Lag HGSD', navn)
        self.assertIn('KO', navn)
        self.assertNotIn('Ambulanse 1', navn, 'bilen står i /oppdrag/ alt')

    def test_navnene_staar_i_norsk_rekkefolge(self):
        """Samme regel som besetningen i `/oppdrag/` (26. sep. 2026)."""
        for navn in ('Åse', 'Ærlig', 'Ola'):
            self._skift(self.res_hgsd, Mannskap.objects.create(navn=navn, korps=self.hgsd))
        rader = {r['navn']: r for r in services.ressurser_uten_enhet()}
        self.assertEqual([m['navn'] for m in rader['Lag HGSD']['mannskap']], ['Ola', 'Ærlig', 'Åse'])

    def test_bemanningen_er_de_som_har_skift_naa(self):
        self._skift(self.res_hgsd, self.p_hgsd, mott_at=self.na)
        self._skift(self.res_hgsd, self.p_karmoy)            # ikke møtt
        rader = {r['navn']: r for r in services.ressurser_uten_enhet()}
        hgsd = rader['Lag HGSD']
        self.assertEqual((hgsd['antall'], hgsd['tilstede']), (2, 1))
        self.assertEqual([m['navn'] for m in hgsd['mannskap']], ['Kari', 'Ola'],
                         'de som er møtt først')
        self.assertNotIn('neste', hgsd, 'et lag uten skift nå er ikke i lista, så «neste» er borte')

    def test_bare_de_med_skift_naa_er_med(self):
        """«Bare de som er på vakt nå» (André, 19. sep. 2026). Et lag hvis
        skift starter senere, gikk ut, eller som ikke har noe skift, vises
        ikke — heller ikke som ubemannet. Grensene selv er innenfor."""
        self._skift(self.res_karmoy, self.p_karmoy, fra=5, til=13)      # senere
        self.assertEqual([r['navn'] for r in services.ressurser_uten_enhet()], [])
        self._skift(self.res_fri, self.p_hgsd, fra=-9, til=-1)           # gikk ut
        self.assertEqual([r['navn'] for r in services.ressurser_uten_enhet()], [])
        self._skift(self.res_hgsd, self.p_hgsd, fra=0, til=0)            # akkurat nå
        rader = services.ressurser_uten_enhet(naa=self.na)
        self.assertEqual([r['navn'] for r in rader], ['Lag HGSD'])
        # Regelen er én, og lagvelgeren i KO leser den samme.
        self.assertEqual([r.pk for r in services.ressurser_paa_vakt_naa(self.vl, self.na)],
                         [self.res_hgsd.pk])

    def test_avmeldte_teller_ikke(self):
        self._skift(self.res_hgsd, self.p_hgsd, avmeldt_at=self.na)
        rader = {r['navn']: r for r in services.ressurser_uten_enhet()}
        self.assertNotIn('Lag HGSD', rader, 'et avmeldt skift er ikke et skift')

    def test_svaret_baerer_telefon_og_issi(self):
        """Var uten til 19. sep. 2026 («et nummer man ikke trenger er et
        nummer på en skjerm i et rom»); André ville ha dem, og kortet viser
        dem først ved klikk. Samme felter som `besetning()` gir bilene."""
        self.p_hgsd.telefon = '99988777'
        self.p_hgsd.issi = '2401234'
        self.p_hgsd.save()
        self._skift(self.res_hgsd, self.p_hgsd)
        rad = next(r for r in services.ressurser_uten_enhet() if r['navn'] == 'Lag HGSD')
        self.assertEqual(set(rad['mannskap'][0]), {'navn', 'rolle', 'tilstede', 'telefon', 'issi'})
        self.assertEqual((rad['mannskap'][0]['telefon'], rad['mannskap'][0]['issi']), ('99988777', '2401234'))

    def test_ingen_liste_gir_tom(self):
        AppSetting.set('aktiv_vakt_id', 999999)
        self.vl.delete()
        self.assertEqual(services.ressurser_uten_enhet(), [])

    def test_gaten_er_vaktlistas_og_krever_alle_korps(self):
        """`les` i vaktliste som bare ser sitt eget korps får ikke alle
        lagene her — samme regel som besetningen (M3)."""
        svar = self.c_leser.get(self.STI)
        self.assertEqual(svar.status_code, 403)
        ModulTilgang.objects.update_or_create(
            bruker=self.leser, modul_slug='oppdrag', defaults={'nivaa': 'les'})
        self._skift(self.res_hgsd, self.p_hgsd)
        svar = self.c_leser.get(self.STI)
        self.assertEqual(svar.status_code, 200)
        self.assertIn('Lag HGSD', [r['navn'] for r in svar.json()['data']])

    def test_uten_vaktlistetilgang_er_det_403(self):
        from accounts.models import CustomUser
        from django.test import Client
        bruker = CustomUser.objects.create_user(
            username='bareoppdrag', password='x', must_change_password=False)
        ModulTilgang.objects.create(bruker=bruker, modul_slug='oppdrag', nivaa='skriv_full')
        c = Client()
        c.force_login(bruker)
        self.assertEqual(c.get(self.STI).status_code, 403)
