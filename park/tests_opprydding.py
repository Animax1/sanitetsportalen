"""Lagregistreringenes lagringstid, håndhevet gjennom `purge_old_logs`.

**Prøvene går gjennom kommandoen, ikke gjennom `services.slett_utlopte()`** —
regel 3 om mutasjoner i `CLAUDE.md`: kaller testen hjelperen selv, kan
registreringen i `apps.ready()` fjernes uten at noe blir rødt, og da gjør
cron-jobben ingenting med radene mens den melder grønt.
"""
from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from core.opprydding import all_handlers

from . import services
from .models import Parklenke, Registrering
from .tests import _Grunnlag


class RegisteretTests(_Grunnlag):

    def test_park_er_registrert_med_fristen_modulen_bruker(self):
        """Utskriften i cron-loggen er det eneste beviset noen ser."""
        handler = next((h for h in all_handlers() if h.slug == 'park'), None)
        self.assertIsNotNone(handler, 'purge_old_logs ville ikke rørt registreringene')
        self.assertEqual(handler.frist_dager(), services.OPPBEVARING_DAGER)

    def test_fristen_er_24_maaneder(self):
        """Tallet personvernbeskrivelsen (B23) oppgir. Flyttes det, skal
        dokumentet følge med — derfor er det låst her og ikke bare i koden."""
        self.assertEqual(services.OPPBEVARING_DAGER, 730)


class KommandoenTests(_Grunnlag):

    def _alder(self, rad, dager, minutter=0):
        Registrering.objects.filter(pk=rad.pk).update(
            registrert_at=timezone.now() - timedelta(days=dager, minutes=minutter))
        return rad

    def _igjen(self):
        return set(Registrering.objects.values_list('pk', flat=True))

    def test_utlopte_slettes_ferske_staar(self):
        gammel = self._alder(self._registrer(), 800)
        fersk = self._registrer()
        call_command('purge_old_logs', stdout=StringIO())
        self.assertEqual(self._igjen(), {fersk.pk})
        self.assertFalse(Registrering.objects.filter(pk=gammel.pk).exists())

    def test_grensen(self):
        """Én time på hver side av fristen — ikke én dag, som ville latt en
        grense av med ett døgn gå grønn."""
        innenfor = self._alder(self._registrer(), services.OPPBEVARING_DAGER - 1, 23 * 60)
        utenfor = self._alder(self._registrer(), services.OPPBEVARING_DAGER, 60)
        call_command('purge_old_logs', stdout=StringIO())
        self.assertEqual(self._igjen(), {innenfor.pk})
        self.assertNotIn(utenfor.pk, self._igjen())

    def test_slettede_rader_foelger_samme_frist(self):
        """Merkingen (B20) er en visning. Grunnen er fritekst fra en leder, og
        skal ikke stå lenger enn raden den forklarer."""
        rad = self._registrer()
        services.slett_registrering(rad, bruker=None, grunn='Feil lag')
        self._alder(rad, 800)
        call_command('purge_old_logs', stdout=StringIO())
        self.assertEqual(self._igjen(), set())

    def test_lenken_og_vakta_staar(self):
        """Registreringene peker på dem, ikke omvendt."""
        self._alder(self._registrer(), 800)
        call_command('purge_old_logs', stdout=StringIO())
        self.assertTrue(Parklenke.objects.filter(pk=self.lenke.pk).exists())
        self.vakt.refresh_from_db()

    def test_torrkjoring_teller_det_samme_og_sletter_ingenting(self):
        self._alder(self._registrer(), 800)
        self._alder(self._registrer(), 900)
        self._registrer()
        torr = StringIO()
        call_command('purge_old_logs', '--dry-run', stdout=torr)
        self.assertIn('Ville slettet 2 lagregistreringer', torr.getvalue())
        self.assertEqual(len(self._igjen()), 3)
        skarp = StringIO()
        call_command('purge_old_logs', stdout=skarp)
        self.assertIn('Slettet 2 lagregistreringer', skarp.getvalue())
        self.assertEqual(len(self._igjen()), 1)

    def test_days_flagget_roerer_ikke_lagene(self):
        """`--days` gjelder rammeverkets tabeller; modulens frist er modulens."""
        self._alder(self._registrer(), 400)
        call_command('purge_old_logs', '--days', '30', stdout=StringIO())
        self.assertEqual(len(self._igjen()), 1)
