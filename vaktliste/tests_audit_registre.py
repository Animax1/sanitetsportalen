"""Hver modell i vaktlista setter spor, eller er unntatt med grunn (26. sep. 2026, B3).

Mannskapet, skiftene, ressursene, pausene og overnattingen ble logget. Men:

- **En vaktliste som ble opprettet eller slettet** — bare `pre_save` var koblet.
- **`timetak`** sto ikke i den håndskrevne feltlista.
- **`Korps`, `Kompetanse`, `Ressursgruppe` og `Ressursrolle`** — modulens docstring
  sa at de «endres fra Django-admin, som har sin egen historikk». Det har ikke
  vært sant siden registrene flyttet inn på `/vaktliste/` (30. aug. 2026), og
  Django-admin er ikke rutet i prod. Å slette en gruppe tar rollene med seg.
- **`Belastningsgrenser`** — endrer varslene for alle lister.

Samme feil som i brukeradmin (B2): jo mer inngripende, jo mindre spor. Regelen
står nå som en test som går gjennom *alle* modellene, så neste modell ikke kan
komme uten at noen tar stilling — samme form som
`BrukerpekereStrippesEllerBegrunnesTests`.
"""
from __future__ import annotations

import json

from django.apps import apps
from django.db.models.signals import post_delete, post_save, pre_save
from django.test import SimpleTestCase

from audit.models import AuditLog

from .models import Belastningsgrenser, Korps, Vaktliste
from .tests_tilgang import TilgangsBasis

#: Modeller som bevisst ikke har mottakere her, og hvorfor.
UNNTATT = {
    'Utsending': 'logges av `fil.send_fil` selv, med utfallet — en rad per forsøk',
}


def _mottakere(signal, modell):
    funnet = signal._live_receivers(modell)
    sync = funnet[0] if isinstance(funnet, tuple) else funnet
    return [r for r in sync if getattr(r, '__module__', '') == 'vaktliste.signals']


class HverModellHarSporTests(SimpleTestCase):

    def test_opprett_endre_slett_eller_begrunnet_unntak(self):
        mangler = []
        for modell in apps.get_app_config('vaktliste').get_models():
            navn = modell.__name__
            if navn in UNNTATT:
                continue
            for signal, hva in ((pre_save, 'endring'), (post_save, 'opprettelse'),
                                (post_delete, 'sletting')):
                if not _mottakere(signal, modell):
                    mangler.append(f'{navn}: {hva}')
        self.assertEqual(mangler, [], 'Koble til i vaktliste/signals.py, eller før opp i UNNTATT')

    def test_unntakene_finnes_og_er_begrunnet(self):
        navn = {m.__name__ for m in apps.get_app_config('vaktliste').get_models()}
        self.assertEqual(sorted(set(UNNTATT) - navn), [])
        self.assertTrue(all(g.strip() for g in UNNTATT.values()))


class RegistreneLoggesTests(TilgangsBasis):
    """Gjennom endepunktene, så det er kallstedet og ikke bare mottakeren som prøves."""

    def _rader(self, tabell, pk=None):
        qs = AuditLog.objects.filter(table_name=tabell)
        if pk is not None:
            qs = qs.filter(record_id=pk)
        return [(r.action, r.field_name, r.old_value, r.new_value, r.user)
                for r in qs.order_by('pk')]

    def test_korps_opprettes_endres_og_slettes(self):
        res = self.c_leder.post('/vaktliste/api/korps/', data={'navn': 'Sola', 'kortnavn': 'SOLA'},
                                content_type='application/json')
        self.assertEqual(res.status_code, 201, res.content)
        pk = res.json()['data']['id']
        self.c_leder.put(f'/vaktliste/api/korps/{pk}/', data={'navn': 'Sola RK'},
                         content_type='application/json')
        self.c_adm.delete(f'/vaktliste/api/korps/{pk}/', data={'confirm': True},
                          content_type='application/json')
        rader = self._rader('vaktliste_korps', pk)
        self.assertEqual([r[0] for r in rader], ['CREATE', 'UPDATE', 'DELETE'])
        self.assertEqual(rader[1][1:4], ('navn', 'Sola', 'Sola RK'))
        self.assertFalse(Korps.objects.filter(pk=pk).exists())

    def test_grensene_logges_med_verdi(self):
        self.c_leder.put('/vaktliste/api/grenser/', data={'maks_skift_timer': 10},
                         content_type='application/json')
        self.assertIn(('UPDATE', 'maks_skift_timer', '12', '10', self.leder),
                      self._rader('vaktliste_belastningsgrenser'))
        self.assertEqual(Belastningsgrenser.hent().maks_skift_timer, 10)

    def test_timetaket_logges(self):
        res = self.c_leder.put(f'/vaktliste/api/vaktlister/{self.vl.pk}/',
                               data={'timetak': 400}, content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn(('UPDATE', 'timetak', '', '400', self.leder),
                      self._rader('vaktliste_vaktliste'))

    def test_vaktlista_opprettes_og_slettes(self):
        res = self.c_leder.post('/vaktliste/api/vaktlister/', data={'navn': 'Høstvakta'},
                                content_type='application/json')
        self.assertEqual(res.status_code, 201, res.content)
        pk = res.json()['data']['id']
        self.c_adm.delete(f'/vaktliste/api/vaktlister/{pk}/', data=json.dumps({'confirm': True}),
                          content_type='application/json')
        handlinger = [r[0] for r in self._rader('vaktliste_vaktliste', pk)
                      if r[0] in ('CREATE', 'DELETE')]
        self.assertEqual(handlinger, ['CREATE', 'DELETE'])
        self.assertFalse(Vaktliste.objects.filter(pk=pk).exists())

    def test_notatet_logges_uten_verdi(self):
        self.vl.notat = 'Kari er gravid'
        self.vl.save()
        rad = AuditLog.objects.get(table_name='vaktliste_vaktliste', field_name='notat')
        self.assertNotIn('gravid', rad.new_value + rad.old_value)
