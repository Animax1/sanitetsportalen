"""Vaktvelgeren i `/statistikk/` — tidligere vakter for alle fanene (steg 3, 28. sep. 2026).

Backend: `core.vaktstatistikk.tidligere_vakter()` og de to endepunktene. Det som
skal holde:

- En avsluttet vakt vises én gang per avslutning, med de frosne tallene.
- Et arkiv fra før frysingen fantes vises for vakter uten frosset sett.
- **Et arkiv uten vakt og med slettede rader vises med tallene sine** — LS2026
  (mai 2026) ligger i prod slik: pasientarkiv, bare frosset aggregat, og
  vaktpekeren tom fordi `patients/0014` ikke fylte den inn.
- Bare global admin, og bare fanene brukeren har de levende tallene til.
"""
from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from core.models import Vakt, VaktStatistikk
from core.vaktstatistikk import tidligere_vakter
from oppdrag.models import OppdragArkiv
from patients.models import VaktArkiv
from patients.test_helpers import sett_aktiv_vakt


def _vakt(navn, **felt):
    return Vakt.objects.create(navn=navn, year=2026, startet=timezone.now(), er_aktiv=False, **felt)


def _frosset(vakt, slug, data, naar):
    return VaktStatistikk.objects.create(vakt=vakt, vakt_navn=vakt.navn, slug=slug,
                                         data=data, frosset_at=naar, versjon=2)


def _pasientarkiv(vakt=None, *, navn='LS2026', kollapset=False, naar=None):
    arkiv = VaktArkiv.objects.create(
        tittel=f'{navn} — arkivert', arrangement_navn=navn, vakt=vakt,
        antall_pasienter=4, year_snapshot=2026)
    felt = {'importert_at': naar or timezone.now()}
    if kollapset:
        felt.update(kollapset_at=timezone.now(),
                    aggregat={'basis': {}, 'full': {'summary': {'total': 4}}})
    VaktArkiv.objects.filter(pk=arkiv.pk).update(**felt)
    return VaktArkiv.objects.get(pk=arkiv.pk)


class TidligereVakterTests(TestCase):

    def setUp(self):
        self.naa = timezone.now()

    def test_et_frosset_sett_er_en_oppforing_med_alle_fanene(self):
        vakt = _vakt('Sommerfest')
        a = _frosset(vakt, 'patients', {'x': 1}, self.naa)
        b = _frosset(vakt, 'park', {'y': 2}, self.naa)
        (oppforing,) = tidligere_vakter()
        self.assertEqual(oppforing['navn'], 'Sommerfest')
        self.assertEqual(oppforing['kilder'], {
            'patients': {'type': 'frosset', 'id': a.pk},
            'park': {'type': 'frosset', 'id': b.pk}})

    def test_gjenaapnet_vakt_har_to_oppforinger(self):
        vakt = _vakt('Sommerfest')
        _frosset(vakt, 'patients', {}, self.naa - timezone.timedelta(hours=5))
        _frosset(vakt, 'patients', {}, self.naa)
        self.assertEqual(len(tidligere_vakter()), 2)

    def test_arkiv_uten_vakt_og_uten_rader_vises(self):
        """LS2026: kollapset pasientarkiv, ingen vaktpeker."""
        arkiv = _pasientarkiv(kollapset=True)
        (oppforing,) = tidligere_vakter()
        self.assertEqual(oppforing['navn'], 'LS2026')
        self.assertEqual(oppforing['kilder'], {'patients': {'type': 'arkiv', 'id': arkiv.pk}})

    def test_to_arkiver_uten_vakt_er_to_oppforinger(self):
        """Uten vakt å samle dem på er hvert arkiv sin egen vakt."""
        _pasientarkiv(navn='LS2025')
        _pasientarkiv(navn='LS2026')
        self.assertEqual(sorted(o['navn'] for o in tidligere_vakter()), ['LS2025', 'LS2026'])

    def test_vakt_med_arkiver_men_uten_frosset_sett(self):
        """Avsluttet før frysingen fantes: tallene står bare i arkivene."""
        vakt = _vakt('Vårfest')
        pas = _pasientarkiv(vakt)
        opp = OppdragArkiv.objects.create(tittel='x', vakt=vakt, vakt_navn=vakt.navn, antall_rader=0)
        (oppforing,) = tidligere_vakter()
        self.assertEqual(oppforing['navn'], 'Vårfest')
        self.assertEqual(oppforing['kilder'], {'patients': {'type': 'arkiv', 'id': pas.pk},
                                               'oppdrag': {'type': 'arkiv', 'id': opp.pk}})

    def test_frosset_sett_skjuler_arkivene_til_samme_vakt(self):
        vakt = _vakt('Sommerfest')
        rad = _frosset(vakt, 'patients', {}, self.naa)
        _pasientarkiv(vakt)
        (oppforing,) = tidligere_vakter()
        self.assertEqual(oppforing['kilder'], {'patients': {'type': 'frosset', 'id': rad.pk}})

    def test_nyeste_forst(self):
        _pasientarkiv(naar=self.naa - timezone.timedelta(days=100))
        _frosset(_vakt('Ny'), 'patients', {}, self.naa)
        self.assertEqual([o['navn'] for o in tidligere_vakter()], ['Ny', 'LS2026'])


@override_settings(SECURE_SSL_REDIRECT=False)
class EndepunkteneTests(TestCase):

    def setUp(self):
        sett_aktiv_vakt(2026)
        self.admin = CustomUser.objects.create_user(
            username='a', password='x', role='admin', must_change_password=False)
        self.leder = CustomUser.objects.create_user(
            username='l', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(self.leder, 'leder')
        self.vakt = _vakt('Sommerfest')
        self.rad = _frosset(self.vakt, 'park', {'summary': {'kontakter': 9}}, timezone.now())

    def _c(self, bruker):
        c = Client()
        c.force_login(bruker)
        return c

    def test_admin_faar_lista(self):
        vakter = self._c(self.admin).get('/statistikk/api/vakter/').json()['vakter']
        self.assertEqual([v['navn'] for v in vakter], ['Sommerfest'])

    def test_bare_global_admin(self):
        """Også for den som ser Lag-fanen for pågående vakt: tidligere vakter er
        strengere beskyttet, som arkivene."""
        from accounts.models import ModulTilgang
        for modul in ('statistikk', 'park'):
            ModulTilgang.objects.update_or_create(
                bruker=self.leder, modul_slug=modul, defaults={'nivaa': 'les'})
        c = self._c(self.leder)
        self.assertEqual(c.get('/statistikk/api/kilde/park/full-stats/').status_code, 200)
        self.assertEqual(c.get('/statistikk/api/vakter/').status_code, 403)
        self.assertEqual(c.get(f'/statistikk/api/kilde/park/frosset/{self.rad.pk}/').status_code, 403)

    def test_de_frosne_tallene_og_versjonen(self):
        svar = self._c(self.admin).get(f'/statistikk/api/kilde/park/frosset/{self.rad.pk}/')
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(svar.json(), {'summary': {'kontakter': 9}})
        self.assertEqual(svar['X-Statistikk-Versjon'], '2')

    def test_raden_maa_hore_til_fanen(self):
        """Pk-en til Lag-tallene skal ikke kunne hentes gjennom pasientfanen."""
        svar = self._c(self.admin).get(f'/statistikk/api/kilde/patients/frosset/{self.rad.pk}/')
        self.assertEqual(svar.status_code, 404)

    def test_ls2026_gjennom_arkivendepunktet(self):
        """Nedtrekket peker på arkivendepunktet, og det leser aggregatet."""
        arkiv = _pasientarkiv(kollapset=True)
        c = self._c(self.admin)
        (ls,) = [v for v in c.get('/statistikk/api/vakter/').json()['vakter'] if v['navn'] == 'LS2026']
        kilde = ls['kilder']['patients']
        self.assertEqual(kilde, {'type': 'arkiv', 'id': arkiv.pk})
        svar = c.get(f'/statistikk/api/kilde/patients/arkiv/{kilde["id"]}/full-stats/')
        self.assertEqual(svar.json(), {'summary': {'total': 4}})

    def test_siden_viser_velgeren_bare_for_admin(self):
        self.assertContains(self._c(self.admin).get('/statistikk/'), 'id="stat-vakt"')
        self.assertNotContains(self._c(self.leder).get('/statistikk/'), 'id="stat-vakt"')
