"""KO-loggens lagringstid, håndhevet gjennom `purge_old_logs`.

**Prøvene går gjennom kommandoen, ikke gjennom `services.slett_utlopte()`.**
Regel 3 i `CLAUDE.md` om mutasjoner: kaller testen hjelperen selv, kan
kallstedet fjernes uten at noe blir rødt — og her *er* kallstedet hele poenget.
Registeret finnes nettopp fordi `audit/` ikke får importere `ko`, og en test
som hopper over registeret ville ikke merket at koblingen røk.
"""
from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from core.opprydding import all_handlers
from core.vakt import hent_aktiv_vakt
from ko import services
from ko.models import Logglinje


class RegisteretTests(TestCase):

    def test_ko_er_registrert(self):
        """Registreres handleren aldri, gjør `purge_old_logs` ingenting med
        loggen — og jobben er fortsatt grønn. Det er nøyaktig den stille
        feilen `DATABASE_URL`-sjekken i `settings.py` finnes for."""
        self.assertIn('ko', [h.slug for h in all_handlers()])

    def test_handleren_oppgir_fristen_modulen_faktisk_bruker(self):
        """Utskriften i cron-loggen er det eneste beviset noen ser. Sier den
        730 mens slettingen bruker 90, er loggen verre enn ingen logg."""
        handler = next(h for h in all_handlers() if h.slug == 'ko')
        self.assertEqual(handler.frist_dager(), services.oppbevaringsdager())


class KommandoenTests(TestCase):

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.bruker = CustomUser.objects.create_user(
            username='ola', password='x', must_change_password=False)

    def _gammel(self, tekst, dager=800):
        linje = services.skriv_linje(self.vakt, tekst, bruker=self.bruker)
        Logglinje.objects.filter(pk=linje.pk).update(
            registrert_at=timezone.now() - timedelta(days=dager))
        return linje

    def test_utlopte_linjer_slettes(self):
        self._gammel('i forfjor')
        services.skriv_linje(self.vakt, 'i dag', bruker=self.bruker)
        call_command('purge_old_logs', stdout=StringIO())
        self.assertEqual(
            list(Logglinje.objects.values_list('tekst', flat=True)), ['i dag'])

    def test_torrkjoring_sletter_ingenting(self):
        """En tørrkjøring som sletter er verre enn ingen tørrkjøring: den
        brukes nettopp for å tørre å kjøre den skarpe etterpå."""
        self._gammel('i forfjor')
        ut = StringIO()
        call_command('purge_old_logs', '--dry-run', stdout=ut)
        self.assertEqual(Logglinje.objects.count(), 1)
        self.assertIn('KO-logglinjer', ut.getvalue())

    def test_torrkjoringen_teller_det_samme_som_slettingen(self):
        """Grensen regnes ut ett sted. To utregninger ville før eller siden
        gitt en tørrkjøring som lovte noe annet enn den skarpe kjøringen
        gjorde."""
        self._gammel('en')
        self._gammel('to')
        services.skriv_linje(self.vakt, 'fersk', bruker=self.bruker)
        tørr = StringIO()
        call_command('purge_old_logs', '--dry-run', stdout=tørr)
        self.assertIn('Ville slettet 2 KO-logglinjer', tørr.getvalue())
        skarp = StringIO()
        call_command('purge_old_logs', stdout=skarp)
        self.assertIn('Slettet 2 KO-logglinjer', skarp.getvalue())

    def test_days_flagget_roerer_ikke_ko(self):
        """**`--days` gjelder rammeverkets tabeller.** Modulenes frister eies
        av modulene, fordi det er modulen som vet hva dataene er — ett flagg
        som stilte på to helt ulike lagringstider samtidig ville vært en felle
        den dagen noen brukte det.
        """
        self._gammel('i fjor', dager=400)
        call_command('purge_old_logs', '--days', '30', stdout=StringIO())
        self.assertEqual(Logglinje.objects.count(), 1)

    def test_en_feilende_handler_gjor_jobben_rod(self):
        """**Å svelge feilen ville gitt en grønn jobb som ikke gjorde det den
        sier.** Ingen ser på mens cron kjører; utskriften og exitkoden er alt.
        """
        from unittest.mock import patch

        with patch('ko.opprydding.services.slett_utlopte',
                   side_effect=RuntimeError('basen er borte')):
            with self.assertRaises(CommandError):
                call_command('purge_old_logs', stdout=StringIO(),
                             stderr=StringIO())

    def test_rammeverkets_rydding_skjer_selv_om_en_modul_feiler(self):
        """Den andre halvdelen av samme valg: å avbryte på den første ville
        latt en modul med en ødelagt spørring holde alle de andre
        lagringstidene uhåndhevet — stille."""
        from unittest.mock import patch

        from core.models import Notification

        gammelt = Notification.objects.create(user=self.bruker, message='x')
        Notification.objects.filter(pk=gammelt.pk).update(
            created_at=timezone.now() - timedelta(days=90))
        with patch('ko.opprydding.services.slett_utlopte',
                   side_effect=RuntimeError('nei')):
            with self.assertRaises(CommandError):
                call_command('purge_old_logs', stdout=StringIO(),
                             stderr=StringIO())
        self.assertFalse(Notification.objects.filter(pk=gammelt.pk).exists())
