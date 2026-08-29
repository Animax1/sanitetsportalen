"""Tester for N2 (fullstendig audit-dekning) og N5 (lokaltid, ikke container-tid).

Kjør med: python manage.py test patients.tests_audit_og_tid
"""
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase, override_settings

from patients.services import vakt_for_year

from audit.models import AuditLog
from core.validators import current_local_year
from patients.models import Patient, Forstehjelper, Helsepersonell
from patients.signals import FELT_UTEN_AUDIT, felt_som_spores


class AuditDekningTests(TestCase):
    """N2: enhver endring av et lagret pasientfelt skal gi en audit-rad."""

    def test_alle_modellfelt_er_daekket(self):
        """Vaktposten mot at et nytt felt faller ut av loggen stilltiende.

        Feiler denne etter at du la til et felt på Patient: legg feltet i
        FELT_UTEN_AUDIT hvis det bevisst ikke skal logges. Ikke bare fjern
        testen — den er grunnlaget for påstanden i A.10 om at alle
        pasientendringer logges på feltnivå.
        """
        sporet = set(felt_som_spores())
        for felt in Patient._meta.concrete_fields:
            with self.subTest(felt=felt.name):
                dekket = (
                    felt.attname in sporet
                    or felt.name in FELT_UTEN_AUDIT
                    or felt.attname in FELT_UTEN_AUDIT
                )
                self.assertTrue(
                    dekket,
                    f'Feltet «{felt.name}» blir verken audit-logget eller '
                    f'eksplisitt unntatt i FELT_UTEN_AUDIT.',
                )

    def test_helsepersonell_endring_logges(self):
        """Selve funnet i N2 — dette ga ingen audit-rad før."""
        hp1 = Helsepersonell.objects.create(name='Sykepleier A')
        hp2 = Helsepersonell.objects.create(name='Sykepleier B')
        pasient = Patient.objects.create(pasientnummer=901, vakt=vakt_for_year(2026), helsepersonell_ref=hp1)

        AuditLog.objects.all().delete()
        pasient.helsepersonell_ref = hp2
        pasient.save()

        rad = AuditLog.objects.get(field_name='helsepersonell_ref_id')
        self.assertEqual(rad.old_value, str(hp1.pk))
        self.assertEqual(rad.new_value, str(hp2.pk))
        self.assertEqual(rad.record_id, pasient.pk)

    def test_forstehjelper_endring_logges_fortsatt(self):
        """Regresjonsvakt: det som virket før, skal fortsatt virke."""
        fh1 = Forstehjelper.objects.create(name='Hjelper A')
        fh2 = Forstehjelper.objects.create(name='Hjelper B')
        pasient = Patient.objects.create(pasientnummer=902, vakt=vakt_for_year(2026), forstehjelper=fh1)

        AuditLog.objects.all().delete()
        pasient.forstehjelper = fh2
        pasient.save()

        self.assertTrue(AuditLog.objects.filter(field_name='forstehjelper_id').exists())

    def test_kliniske_felt_logges(self):
        pasient = Patient.objects.create(pasientnummer=903, vakt=vakt_for_year(2026))
        AuditLog.objects.all().delete()

        pasient.problemstilling = 'Skade'
        pasient.transport = 'Baare'
        pasient.save()

        loggede = set(AuditLog.objects.values_list('field_name', flat=True))
        self.assertEqual(loggede, {'problemstilling', 'transport'})

    def test_updated_at_gir_ikke_auditrad(self):
        """auto_now-feltet ville ellers gitt en rad ved hver eneste lagring."""
        pasient = Patient.objects.create(pasientnummer=904, vakt=vakt_for_year(2026))
        AuditLog.objects.all().delete()

        pasient.problemstilling = 'Noe'
        pasient.save()

        self.assertFalse(AuditLog.objects.filter(field_name='updated_at').exists())

    def test_deaktivering_logges_som_delete(self):
        pasient = Patient.objects.create(pasientnummer=905, vakt=vakt_for_year(2026))
        AuditLog.objects.all().delete()

        pasient.is_active = False
        pasient.save()

        rad = AuditLog.objects.get(field_name='is_active')
        self.assertEqual(rad.action, 'DELETE')


@override_settings(TIME_ZONE='Europe/Oslo', USE_TZ=True)
class LokaltAarTests(TestCase):
    """N5: året skal utledes i Europe/Oslo, ikke i containerens UTC."""

    def _frys(self, iso_utc):
        """Frys django.utils.timezone.now() til et gitt UTC-tidspunkt."""
        tidspunkt = datetime.fromisoformat(iso_utc).replace(tzinfo=dt_timezone.utc)
        return patch('django.utils.timezone.now', return_value=tidspunkt)

    def test_nyttaarsaften_2330_utc_gir_neste_aar(self):
        """23:30 UTC 31. desember er 00:30 norsk tid 1. januar.

        Container-tid ville gitt året som nettopp gikk. En nyttårsvakt ville
        registrert pasienter på feil år, og listevisningen ville vært konsistent
        med seg selv — så feilen ville ikke blitt sett før i statistikken.
        """
        with self._frys('2026-12-31T23:30:00'):
            self.assertEqual(current_local_year(), 2027)

    def test_midt_paa_dagen_gir_samme_aar(self):
        with self._frys('2026-06-15T12:00:00'):
            self.assertEqual(current_local_year(), 2026)

    def test_nyttaarsaften_2200_utc_er_fortsatt_gammelt_aar(self):
        """23:00 norsk tid — grensen har ikke passert ennå."""
        with self._frys('2026-12-31T22:00:00'):
            self.assertEqual(current_local_year(), 2026)

    def test_patient_save_bruker_lokalt_aar(self):
        """`Patient.save` uten vakt faller tilbake til aktiv vakt, som på
        fersk base opprettes for *lokalt* år — samme N5-poeng, ny mekanisme
        (year-kolonnen forsvant i deploy 2)."""
        with self._frys('2026-12-31T23:30:00'):
            pasient = Patient.objects.create(pasientnummer=906)
        self.assertEqual(pasient.vakt.year, 2027)

    def test_hent_aktiv_vakt_bruker_lokalt_aar(self):
        """Fallbacken i `hent_aktiv_vakt` (ingen peker, ingen vakter) skal
        lage vakta for lokalt år, ikke containerens UTC-år."""
        from patients.services import hent_aktiv_vakt

        with self._frys('2026-12-31T23:30:00'):
            self.assertEqual(hent_aktiv_vakt().year, 2027)


class IngenNaivDatetimeTests(TestCase):
    """N5s akseptansekriterium: ingen datetime.now() i kode som utleder tid."""

    def test_ingen_datetime_now_i_patients_og_core(self):
        """Bruker AST og ikke tekstsøk, slik at omtale i docstrings og
        feilmeldinger ikke gir falske treff — kun faktiske kall telles."""
        import ast
        from pathlib import Path
        from django.conf import settings

        treff = []
        for mappe in ['patients', 'core']:
            for fil in Path(settings.BASE_DIR, mappe).rglob('*.py'):
                # Migrasjoner er frosset historikk og skal ikke endres.
                if 'migrations' in fil.parts:
                    continue
                tre = ast.parse(fil.read_text(encoding='utf-8'), filename=str(fil))
                for node in ast.walk(tre):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == 'now'
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == 'datetime'
                    ):
                        treff.append(
                            f'{fil.relative_to(settings.BASE_DIR)}:{node.lineno}'
                        )

        self.assertEqual(
            treff, [],
            'datetime.now() gir naiv container-tid (UTC på Railway). '
            'Bruk now_local_str() eller current_local_year() fra core.validators.',
        )
