"""KOs felt på portalinnstillingssiden: oppbevaringstiden.

**Valget som prøves er `AppSetting` framfor en Railway-variabel** (André,
17. sep. 2026). Begrunnelsen står i `ko/services.py`; her prøves de tre
egenskapene den begrunnelsen hviler på: at verdien lar seg endre uten deploy,
at endringen **auditlogges**, og at en ugyldig verdi stopper hele innsendingen
i stedet for å lagre halve skjemaet.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from audit.models import AuditLog
from core.models import AppSetting
from core.portalinnstillinger import all_handlers
from core.signals import nokkel_logges
from ko import services
from ko.portalinnstillinger import KoInnstillinger


class HandlerenTests(TestCase):

    def setUp(self):
        self.handler = KoInnstillinger()

    def test_ko_er_registrert(self):
        self.assertIn('ko', [h.slug for h in all_handlers()])

    def test_gyldig_verdi_lagres(self):
        verdier = self.handler.valider({'ko_logg_dager': '365'})
        self.handler.lagre(verdier)
        self.assertEqual(services.oppbevaringsdager(), 365)

    def test_fravaerende_felt_beholder_verdien(self):
        """**En modul som kan lamme naboene sine ved å mangle en nøkkel, er
        feil bygget.** Et avslag her ville tatt ned hele innstillingssiden —
        arrangementsnavnet og vaktlistas felter med — fordi KO ikke fant sitt.
        """
        AppSetting.set(services.DAGER_NOKKEL, 365)
        verdier = self.handler.valider({})
        self.handler.lagre(verdier)
        self.assertEqual(services.oppbevaringsdager(), 365)

    def test_tomt_felt_avvises(self):
        """Fraværende og tomt er to ting: tomt betyr at et menneske har tømt
        feltet, og da skal hun få vite at en oppbevaringstid ikke kan være
        ingenting."""
        with self.assertRaises(ValidationError):
            self.handler.valider({'ko_logg_dager': ''})

    def test_ikke_et_tall_avvises(self):
        with self.assertRaises(ValidationError):
            self.handler.valider({'ko_logg_dager': 'to år'})

    def test_utenfor_grensene_avvises(self):
        for raa in ('0', '1', str(services.DAGER_MAKS + 1)):
            with self.subTest(raa=raa):
                with self.assertRaises(ValidationError):
                    self.handler.valider({'ko_logg_dager': raa})

    def test_grensene_selv_er_lov(self):
        """Av-med-én, begge veier."""
        for raa in (str(services.DAGER_MIN), str(services.DAGER_MAKS)):
            with self.subTest(raa=raa):
                self.handler.valider({'ko_logg_dager': raa})

    def test_valider_skriver_ingenting(self):
        """**`valider()` og `lagre()` er delt i to** fordi navnet skrives på
        `Vakt` og resten i `AppSetting`, uten en transaksjon mellom seg: en
        modul som nekter skal stoppe hele innsendingen, også portalens egne
        felter."""
        self.handler.valider({'ko_logg_dager': '365'})
        self.assertFalse(
            AppSetting.objects.filter(key=services.DAGER_NOKKEL).exists())


class FristenAuditloggesTests(TestCase):
    """**Hele forskjellen på en `AppSetting` og en Railway-variabel.**

    En oppbevaringstid som endres uten et spor er en oppbevaringstid ingen kan
    revidere — og det er nettopp revisjonen `purge_old_logs` sin egen docstring
    argumenterer for når den sier at grensene ikke skal ligge i «en skjult
    jobbkonfigurasjon».
    """

    def test_nokkelen_er_ikke_unntatt_audit(self):
        """`NOKLER_UTEN_AUDIT` er for tellere maskinen har talt. Fristen er
        noe et menneske har bestemt, og skal aldri inn der."""
        self.assertTrue(nokkel_logges(services.DAGER_NOKKEL))

    def test_endring_gir_en_auditrad(self):
        AppSetting.set(services.DAGER_NOKKEL, 730)
        AppSetting.set(services.DAGER_NOKKEL, 90)
        rader = AuditLog.objects.filter(field_name=services.DAGER_NOKKEL)
        self.assertTrue(rader.exists())
        siste = rader.latest('pk')
        self.assertEqual(siste.new_value, '90')
