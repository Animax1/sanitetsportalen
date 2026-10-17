"""Isolasjonen mellom portalene (17. okt. 2026, `docs/BESLUTNING_PORTALER.md` §6.1).

**Hvorfor dette er en test og ikke en gjennomgang.** Isolasjonen er en regel som
må gjelde *hvert* sted: én modell uten vei til en portal er en tabell der Brann
og Landsskytter deler rader. En manuell gjennomgang holder bare til neste modell
— samme grunn som `patients/tests_modul_dekorator.py` går gjennom `urlpatterns`.

To deler:

1. **Hver modell har en vei til portalen** — en fremmednøkkel, direkte eller
   gjennom vakta eller en forelder — **eller** står i `GLOBALE` med en grunn. En
   ny modell uten noen av delene gjør testen rød.
2. **Én test per modul med to portaler**, som krever at den ene portalens rader
   ikke står i den andres svar. Den første delen ser at kolonnen finnes; denne
   ser at spørringene bruker den.

`VENTER` er modellene som får portal i resten av fase 4 (4b–4d). Den skal bare
krympe, og testen krever det: en modell som har fått en vei, må ut av lista.
"""
from __future__ import annotations

from django.apps import apps
from django.test import Client, SimpleTestCase, TestCase, override_settings

#: Appene som bærer data. `django.*`, `django_otp` m.fl. er ikke våre.
APPER = ('patients', 'oppdrag', 'vaktliste', 'ko', 'park', 'statistikk', 'backlog',
         'accounts', 'audit', 'core')

MAAL = {'core.Vaktportal', 'core.Vakt'}

#: Modeller som med vilje er felles for alle portaler. **Grunnen står ved hver**,
#: og regelen bak de fleste er §4.12: det som beskriver faget er globalt.
GLOBALE = {
    'accounts.CustomUser': 'Én innlogging, én MFA — medlemskapet er per portal',
    'accounts.LoginEvent': 'Innloggingsloggen gjelder kontoen, ikke en portal',
    'audit.AuditLog': 'Revisjonsloggen er systemets',
    'core.ModuleSettings': 'Modulene slås av og på for hele installasjonen',
    'core.Backupplan': 'Backup er per modul, ikke per portal (§5)',
    'core.Backup': 'Backup er per modul, ikke per portal (§5)',
    'core.OffsiteKopi': 'Backup er per modul, ikke per portal (§5)',
    'core.AppSetting': 'Nøkkel/verdi; portalens nøkler sorteres i fase 4d (§4.7)',
    'core.Tilhorighet': 'Den felles katalogen (beslutning 9) — portalen velger sine',
    'core.Kontotilhorighet': 'Hører til kontoen, som er global',
    'oppdrag.Enhet': 'Bilene er globale (beslutning 12)',
    'oppdrag.Enhetstype': 'Fag — følger bilene, som er globale (§4.12)',
    'oppdrag.Problemstilling': 'Fag (§4.12)',
    'oppdrag.Lydvarsel': 'Bilens lydvarsel per hastegrad — fag, som hastegraden',
    'vaktliste.Kompetanse': 'Organisasjonens kompetansestige (§4.12)',
    'vaktliste.Ressursgruppe': 'Seedet, og typen er fag (§4.12)',
    'vaktliste.Ressursrolle': 'Hører til ressursgruppa, som er global',
    'vaktliste.Belastningsgrenser': 'Organisasjonens grenser for alle vaktlister',
    'park.Problemstilling': 'Fag (§4.12, avgjort 17. okt. 2026)',
    'park.Utfall': 'Fag (§4.12, avgjort 17. okt. 2026)',
    'backlog.Innspilltype': 'Backlog står utenfor vaktscopet (`backlog/CLAUDE.md`)',
    'backlog.Innspill': 'Backlog står utenfor vaktscopet (`backlog/CLAUDE.md`)',
    'backlog.Kommentar': 'Backlog står utenfor vaktscopet (`backlog/CLAUDE.md`)',
}

#: Får portal i resten av fase 4. **Skal bare krympe.**
VENTER = {
    'patients.Forstehjelper': '4b — personnavn (§4.12)',
    'patients.Helsepersonell': '4b — personnavn (§4.12)',
    'oppdrag.Lokasjon': '4b — et sted (§4.12)',
    'ko.Ansvarsomraade': '4c — satt opp per arrangement',
    'ko.Ansvarsmerke': '4c — henger på medlemskapet (beslutning 24)',
    'ko.Konserttype': '4c — artistene er per arrangement',
    'ko.Kjennetegn': '4c — satt opp per arrangement',
    'park.Parklenke': '4c — lenken må bære portalen (§4.13)',
    'park.SkjultSted': '4c — følger lokasjonen',
    'core.Notification': '4d — varslene får portal (§4.14)',
}


def vei_til_portal(modell, dybde=0, sett=frozenset()):
    """Feltnavnene fra `modell` til en portal, eller ``None``. Bare fremmednøkler framover."""
    if modell._meta.label in MAAL:
        return [modell._meta.label]
    if dybde > 4:
        return None
    for felt in modell._meta.get_fields():
        if not (getattr(felt, 'concrete', False) and (felt.many_to_one or felt.one_to_one)):
            continue
        mal = felt.related_model
        if mal is None or mal._meta.label in sett:
            continue
        vei = vei_til_portal(mal, dybde + 1, sett | {modell._meta.label})
        if vei:
            return [felt.name, *vei]
    return None


class HverModellHarEnVeiTests(SimpleTestCase):

    def _modeller(self):
        for app in APPER:
            yield from apps.get_app_config(app).get_models()

    def test_hver_modell_har_en_vei_eller_en_grunn(self):
        uten = [m._meta.label for m in self._modeller()
                if vei_til_portal(m) is None
                and m._meta.label not in GLOBALE and m._meta.label not in VENTER]
        self.assertEqual(uten, [], (
            'Modeller uten vei til en portal, og uten grunn i GLOBALE:\n  '
            + '\n  '.join(uten)
            + '\n\nGi modellen en vei (`core.models.PortalEid`, eller en peker til vakta), '
              'eller før den opp i GLOBALE med hvorfor den er felles for alle portaler.'))

    def test_venter_krymper(self):
        """En modell som har fått en vei, skal ut av `VENTER` — ellers forteller
        lista om arbeid som er gjort."""
        ferdige = [label for label in VENTER if vei_til_portal(apps.get_model(label))]
        self.assertEqual(ferdige, [], f'Har fått en vei til portalen — ta dem ut av VENTER: {ferdige}')

    def test_listene_navngir_modeller_som_finnes(self):
        for label in [*GLOBALE, *VENTER]:
            with self.subTest(label=label):
                apps.get_model(label)

    def test_en_global_modell_har_ikke_en_vei(self):
        """Har den fått en vei, er den ikke global lenger — og grunnen lyver."""
        med_vei = [label for label in GLOBALE if vei_til_portal(apps.get_model(label))]
        self.assertEqual(med_vei, [])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VaktlistaHolderPortaleneAdskiltTests(TestCase):
    """Mannskapet er per portal (§4.5): Brann ser bare sitt eget."""

    def setUp(self):
        from accounts.models import CustomUser
        from accounts.test_helpers import gi_modultilgang
        from core.models import Tilhorighet, Vaktportal
        from core.portal import aktiver_portal, eneste_portal
        from vaktliste.models import Mannskap

        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.hgsd = Tilhorighet.objects.create(navn='HGSD')
        self.standard.tilhorigheter.add(self.hgsd)
        self.brann.tilhorigheter.add(self.hgsd)
        self.kari = CustomUser.objects.create_user(username='kari', password='x',
                                                   must_change_password=False)
        with aktiver_portal(self.brann):
            self.i_brann = Mannskap.objects.create(navn='Bjørn Brann', korps=self.hgsd,
                                                   telefon='11111111', user=self.kari)
        with aktiver_portal(self.standard):
            self.i_standard = Mannskap.objects.create(navn='Stine Standard', korps=self.hgsd,
                                                      telefon='22222222', user=self.kari)
        self.leder = CustomUser.objects.create_user(username='leder', password='x',
                                                    must_change_password=False)
        gi_modultilgang(bruker=self.leder, modul_slug='vaktliste', nivaa='skriv_leder',
                        portal=self.brann)
        self.c = Client()
        self.c.force_login(self.leder)

    def test_mannskapsregisteret_er_portalens(self):
        svar = self.c.get('/vaktliste/api/mannskap/').json()['data']['mannskap']
        self.assertEqual([m['navn'] for m in svar], ['Bjørn Brann'])
        self.assertNotIn('22222222', str(svar))

    def test_en_person_fra_en_annen_portal_kan_ikke_aapnes(self):
        svar = self.c.put(f'/vaktliste/api/mannskap/{self.i_standard.pk}/',
                          content_type='application/json', data={'telefon': '33333333'})
        self.assertEqual(svar.status_code, 404)
        self.i_standard.refresh_from_db()
        self.assertEqual(self.i_standard.telefon, '22222222')

    def test_samme_konto_er_mannskap_i_begge(self):
        """Én-til-én-koblingen ble per portal (beslutning 24)."""
        self.assertEqual(self.i_brann.user, self.i_standard.user)

    def test_ny_person_havner_i_portalen(self):
        from vaktliste.models import Mannskap
        svar = self.c.post('/vaktliste/api/mannskap/', content_type='application/json',
                           data={'navn': 'Ny Nysen', 'korps_id': self.hgsd.pk})
        self.assertEqual(svar.status_code, 201, svar.content)
        self.assertEqual(Mannskap.objects.get(navn='Ny Nysen').portal, self.brann)

    def test_kontoens_korps_er_per_portal(self):
        from core.portal import aktiver_portal
        from vaktliste import services
        from vaktliste.models import Kontokorps, Tilhorighet
        sola = Tilhorighet.objects.create(navn='Sola')
        self.brann.tilhorigheter.add(sola)
        with aktiver_portal(self.brann):
            Kontokorps.objects.create(user=self.leder, korps=sola)
        with aktiver_portal(self.standard):
            self.assertIsNone(services.brukerens_korps(self.leder))
        with aktiver_portal(self.brann):
            self.assertEqual(services.brukerens_korps(self.leder), sola)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VaktlistasKallstederTests(VaktlistaHolderPortaleneAdskiltTests):
    """Ett kallsted per test (mutantene 6–14 i fase 4a overlevde første runde).

    Regelen sto i `i_portal()`, og testene over gikk gjennom registeret — men
    ikke gjennom plassene, overnattingen, kontoens korps eller e-postkoblingen.
    Hvert av dem kunne slått opp i hele tabellen uten at noe ble rødt."""

    def setUp(self):
        super().setUp()
        from django.db import transaction
        from django.utils import timezone

        from core.portal import aktiver_portal
        from core.vakt import gjor_aktiv, opprett_vakt
        from vaktliste.models import Vaktliste, Vaktpost
        from vaktliste.test_helpers import lag_ressurs
        with aktiver_portal(self.brann):
            vakt = opprett_vakt('Kamp 7', year=2026, startet=timezone.now())
        with transaction.atomic():
            gjor_aktiv(vakt)
        self.vl = Vaktliste.objects.create(vakt=vakt)
        self.bil = lag_ressurs(vaktliste=self.vl, navn='Bil 1')
        self.plass = Vaktpost.objects.create(ressurs=self.bil, fra_tid=timezone.now(),
                                             til_tid=timezone.now())

    def _ny_plass(self, person):
        from datetime import timedelta

        from django.utils import timezone
        fra = timezone.now()
        return self.c.post(f'/vaktliste/api/ressurser/{self.bil.pk}/vaktposter/',
                           content_type='application/json',
                           data={'mannskap_id': person.pk, 'fra_tid': fra.isoformat(),
                                 'til_tid': (fra + timedelta(hours=8)).isoformat()})

    def test_en_person_fra_en_annen_portal_settes_ikke_paa_en_ny_plass(self):
        """Med motprøve: den samme forespørselen med portalens egen person går
        gjennom, så 400 kommer av portalen og ikke av noe annet i kroppen."""
        self.assertEqual(self._ny_plass(self.i_standard).status_code, 400)
        self.assertEqual(self._ny_plass(self.i_brann).status_code, 201)

    def test_en_person_fra_en_annen_portal_byttes_ikke_inn(self):
        svar = self.c.put(f'/vaktliste/api/vaktposter/{self.plass.pk}/',
                          content_type='application/json',
                          data={'mannskap_id': self.i_standard.pk})
        self.assertEqual(svar.status_code, 400)
        self.plass.refresh_from_db()
        self.assertIsNone(self.plass.mannskap_id)

    def test_en_person_fra_en_annen_portal_faar_ikke_seng(self):
        """Med motprøve, som over: en gyldig natt, og portalens egen person får plass."""
        from vaktliste import overnatting
        natt = overnatting.netter_i_vakta(self.vl)[0].isoformat()
        rom = overnatting.lagre_rom(self.vl, {'navn': 'Gymsal'})

        def plasser(person):
            return self.c.post(f'/vaktliste/api/overnattingsrom/{rom.pk}/plasser/',
                               content_type='application/json',
                               data={'mannskap_id': person.pk, 'netter': [natt]})
        self.assertEqual(plasser(self.i_standard).status_code, 400)
        self.assertEqual(plasser(self.i_brann).status_code, 201)

    def test_mannskapsraden_i_en_annen_portal_gir_ikke_korps(self):
        from accounts.models import CustomUser
        from core.portal import aktiver_portal
        from vaktliste import services
        from vaktliste.models import Mannskap
        per = CustomUser.objects.create_user(username='per', password='x')
        with aktiver_portal(self.standard):
            Mannskap.objects.create(navn='Per', korps=self.hgsd, user=per)
            self.assertEqual(services.brukerens_korps(per), self.hgsd)
        with aktiver_portal(self.brann):
            self.assertIsNone(services.brukerens_korps(per))

    def test_nedtrekket_tilbyr_bare_portalens_folk(self):
        from core.portal import aktiver_portal
        from vaktliste import services
        setattr(self.leder, '_aktiv_portal', self.brann)
        with aktiver_portal(self.brann):
            navn = [m.navn for m in services.mannskap_brukeren_kan_sette(self.leder)]
        self.assertEqual(navn, ['Bjørn Brann'])

    def test_kontoens_korps_fra_en_annen_portal_vises_ikke_i_skjemaet(self):
        from core.portal import aktiver_portal
        from vaktliste.kontokobling import KontokorpsForm
        from vaktliste.models import Kontokorps
        with aktiver_portal(self.standard):
            Kontokorps.objects.create(user=self.kari, korps=self.hgsd)
        with aktiver_portal(self.brann):
            self.assertIsNone(KontokorpsForm(self.kari).naa)

    def test_korpsregelen_gjelder_innen_portalen(self):
        """Mannskap i HGSD i Standard hindrer ikke å føre Sola i Brann."""
        from accounts.models import CustomUser
        from core.models import Tilhorighet
        from core.portal import aktiver_portal
        from vaktliste.models import Kontokorps, Mannskap
        per = CustomUser.objects.create_user(username='per', password='x')
        sola = Tilhorighet.objects.create(navn='Sola')
        self.brann.tilhorigheter.add(sola)
        with aktiver_portal(self.standard):
            Mannskap.objects.create(navn='Per', korps=self.hgsd, user=per)
        with aktiver_portal(self.brann):
            Kontokorps.objects.create(user=per, korps=sola)   # kaster ikke

    def test_en_konto_koblet_i_en_annen_portal_kobles_her_ogsaa(self):
        from accounts.models import CustomUser
        from vaktliste.models import Mannskap
        ola = CustomUser.objects.create_user(username='ola', password='x', email='ola@ex.no')
        from core.portal import aktiver_portal
        with aktiver_portal(self.standard):
            Mannskap.objects.create(navn='Ola S', korps=self.hgsd, user=ola)
        svar = self.c.post('/vaktliste/api/mannskap/', content_type='application/json',
                           data={'navn': 'Ola B', 'korps_id': self.hgsd.pk, 'epost': 'ola@ex.no'})
        self.assertEqual(svar.status_code, 201, svar.content)
        self.assertEqual(Mannskap.objects.get(navn='Ola B').user, ola)

    def test_kontolista_viser_koblingen_i_portalen(self):
        from core.portal import aktiver_portal
        from vaktliste.views_registre import _kontoer
        with aktiver_portal(self.brann):
            rad = next(r for r in _kontoer() if r['id'] == self.kari.pk)
        self.assertEqual(rad['mannskap_id'], self.i_brann.pk)
        with aktiver_portal(self.standard):
            rad = next(r for r in _kontoer() if r['id'] == self.kari.pk)
        self.assertEqual(rad['mannskap_id'], self.i_standard.pk)
