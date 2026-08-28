"""Tester for serverside-validering av kliniske felt (verdimengde).

To formål:

1. **Drift-vakt:** verdimengden finnes både i ``patients/choices.py`` og som
   ``<option>``/radioknapper i ``templates/patients/index.html``. Kommer de i
   utakt, blir enten et lovlig valg i grensesnittet avvist av API-et, eller et
   felt slutter å være validert. Testene under leser malen og sammenligner.

2. **Regresjonsvern:** API-et skal avvise verdier utenfor mengden. Uten dette
   kunne en klient som gikk utenom grensesnittet lagre fritekst — i verste
   fall navn eller fødselsnummer — i felt som skal være ikke-identifiserende.
   Se docs/PERSONVERN_DOKUMENTASJON.md A.6 og A.12.

Kjør med: python manage.py test patients.tests_choices
"""
import json
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase, Client, override_settings

from accounts.models import CustomUser
from patients.models import Patient, AppSetting
from patients import choices
from patients.choices import validate_patient_choice_fields
from accounts.test_helpers import gi_standardtilgang


def _template_source():
    path = settings.BASE_DIR / 'templates' / 'patients' / 'index.html'
    return path.read_text(encoding='utf-8')


def _select_options(src, element_id):
    """Returner verdiene i en <select> med gitt id, uten placeholder-raden."""
    m = re.search(
        r'<select[^>]*id="%s"[^>]*>(.*?)</select>' % re.escape(element_id),
        src,
        re.S,
    )
    if m is None:
        return None
    raw = re.findall(r'<option[^>]*>([^<]*)</option>', m.group(1))
    # Placeholder er «– Velg –» med tom value; den er ikke en lagringsverdi.
    return [o.strip() for o in raw if o.strip() and not o.strip().startswith('–')]


# Felt → id-er i malen. Noen felt finnes kun i redigeringsskjemaet.
FIELD_TO_ELEMENT_IDS = {
    'problemstilling': ['n-problemstilling', 'e-problemstilling'],
    'arsak': ['n-arsak', 'e-arsak'],
    'transport': ['n-transport', 'e-transport'],
    'plassering': ['n-plassering', 'e-plassering'],
    'utskrevet_til': ['e-utskrevet-til'],
    'lege': ['e-lege'],
    'medisiner': ['e-medisiner'],
    'journal': ['e-journal'],
}


class TemplateDriftTests(TestCase):
    """Malen og choices.py skal alltid være enige om verdimengden."""

    @classmethod
    def setUpTestData(cls):
        cls.src = _template_source()

    def test_dropdowns_matcher_choices(self):
        for field, element_ids in FIELD_TO_ELEMENT_IDS.items():
            forventet = list(choices.CHOICE_FIELDS[field])
            for element_id in element_ids:
                with self.subTest(field=field, element=element_id):
                    faktisk = _select_options(self.src, element_id)
                    self.assertIsNotNone(
                        faktisk,
                        f'Fant ikke <select id="{element_id}"> i index.html. '
                        f'Er skjemaet endret? Oppdater FIELD_TO_ELEMENT_IDS '
                        f'eller patients/choices.py.',
                    )
                    self.assertEqual(
                        faktisk,
                        forventet,
                        f'Verdimengden for «{field}» i #{element_id} er i utakt '
                        f'med patients/choices.py. Oppdater begge.',
                    )

    def test_grovsortering_radioknapper_matcher_choices(self):
        """Triage er radioknapper, ikke <select> – sjekkes separat."""
        verdier = re.findall(r'name="n-triage"[^>]*value="([^"]+)"', self.src)
        self.assertEqual(
            verdier,
            list(choices.GROVSORTERING),
            'Triage-radioknappene i index.html er i utakt med '
            'choices.GROVSORTERING.',
        )


class ValidatorUnitTests(TestCase):
    """Validatoren isolert, uten HTTP."""

    def test_gyldig_verdi_gaar_gjennom(self):
        data = {'problemstilling': 'Brystsmerter'}
        validate_patient_choice_fields(data)
        self.assertEqual(data['problemstilling'], 'Brystsmerter')

    def test_fritekst_avvises(self):
        """Kjernescenarioet: navn skal ikke kunne lagres i et klinisk felt."""
        with self.assertRaises(ValidationError):
            validate_patient_choice_fields({'problemstilling': 'Ola Nordmann, f. 12.03.1990'})

    def test_tom_verdi_er_lov(self):
        """Feltet er ikke utfylt ennå – normalt tidlig i et pasientforløp."""
        data = {'problemstilling': '', 'arsak': None}
        validate_patient_choice_fields(data)
        self.assertEqual(data['problemstilling'], '')
        self.assertEqual(data['arsak'], '')

    def test_felt_som_mangler_roeres_ikke(self):
        """Delvis oppdatering skal ikke tvinge klienten til å sende alt."""
        data = {'problemstilling': 'Kramper'}
        validate_patient_choice_fields(data)
        self.assertNotIn('arsak', data)

    def test_whitespace_trimmes(self):
        data = {'grovsortering': '  Rød  '}
        validate_patient_choice_fields(data)
        self.assertEqual(data['grovsortering'], 'Rød')

    def test_alle_feil_samles_i_en_runde(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_patient_choice_fields({
                'problemstilling': 'tull',
                'arsak': 'tøys',
            })
        self.assertEqual(len(ctx.exception.messages), 2)

    def test_feilmelding_lister_tillatte_verdier(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_patient_choice_fields({'grovsortering': 'Blå'})
        self.assertIn('Grønn', ctx.exception.messages[0])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ChoiceValidationAPITests(TestCase):
    """Validering gjennom det faktiske API-et."""

    def setUp(self):
        AppSetting.objects.update_or_create(
            key='active_year', defaults={'value': '2026'})
        self.user = CustomUser.objects.create_user(
            username='skriver', password='pass', role='read_write',
            must_change_password=False,
        )
        gi_standardtilgang(self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def _post(self, data):
        return self.client.post(
            '/pasienter/api/patients/',
            data=json.dumps(data),
            content_type='application/json',
        )

    def _put(self, pk, data):
        return self.client.put(
            f'/pasienter/api/patients/{pk}/',
            data=json.dumps(data),
            content_type='application/json',
        )

    def test_opprettelse_med_gyldig_verdi(self):
        resp = self._post({
            'problemstilling': 'Pustevansker',
            'grovsortering': 'Gul',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            Patient.objects.get().problemstilling, 'Pustevansker')

    def test_opprettelse_med_fritekst_avvises(self):
        resp = self._post({'problemstilling': 'Kari Nordmann 01019012345'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(
            Patient.objects.exists(),
            'Pasienten skal ikke opprettes når valideringen feiler.',
        )

    def test_opprettelse_avviser_ugyldig_triage(self):
        resp = self._post({'grovsortering': 'Svart'})
        self.assertEqual(resp.status_code, 400)

    def test_oppdatering_med_fritekst_avvises_og_endrer_ingenting(self):
        self._post({'problemstilling': 'Kramper'})
        p = Patient.objects.get()

        resp = self._put(p.pk, {'problemstilling': 'fritekst som ikke er lov'})
        self.assertEqual(resp.status_code, 400)

        p.refresh_from_db()
        self.assertEqual(p.problemstilling, 'Kramper')

    def test_oppdatering_med_gyldig_verdi(self):
        self._post({'problemstilling': 'Kramper'})
        p = Patient.objects.get()

        resp = self._put(p.pk, {'problemstilling': 'Brannskade'})
        self.assertEqual(resp.status_code, 200)

        p.refresh_from_db()
        self.assertEqual(p.problemstilling, 'Brannskade')

    def test_lege_og_journal_er_ja_nei_flagg(self):
        """Begge er Ja/Nei – ikke navn og ikke journalinnhold."""
        self._post({'problemstilling': 'Kramper'})
        p = Patient.objects.get()

        self.assertEqual(self._put(p.pk, {'lege': 'Ja'}).status_code, 200)
        self.assertEqual(self._put(p.pk, {'journal': 'Nei'}).status_code, 200)
        self.assertEqual(
            self._put(p.pk, {'lege': 'Dr. Hansen'}).status_code, 400)
