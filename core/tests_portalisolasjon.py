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


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class HjelperneOgStedeneTests(TestCase):
    """Fase 4b: personnavn og steder er per portal (§4.12).

    Ett kallsted per test, og hver avvisning har en motprøve med portalens egen
    rad — ellers kan 400 komme av noe annet i kroppen, og mutanten som fjerner
    `i_portal()` går grønn (tre slike i fase 4a)."""

    def setUp(self):
        from django.core.cache import cache
        from django.db import transaction
        from django.utils import timezone

        from accounts.models import CustomUser
        from accounts.test_helpers import gi_modultilgang
        from core.models import Vaktportal
        from core.portal import aktiver_portal, eneste_portal
        from core.vakt import gjor_aktiv, opprett_vakt
        from oppdrag.models import Lokasjon
        from patients.models import Forstehjelper, Helsepersonell

        cache.clear()
        self.addCleanup(cache.clear)
        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.kari = CustomUser.objects.create_user(username='kari', password='x',
                                                   must_change_password=False)
        with aktiver_portal(self.standard):
            self.fh_s = Forstehjelper.objects.create(name='Ola', user=self.kari)
            self.hp_s = Helsepersonell.objects.create(name='Lege S')
            self.sted_s = Lokasjon.objects.create(navn='Scene S')
        with aktiver_portal(self.brann):
            self.fh_b = Forstehjelper.objects.create(name='Ola', user=self.kari)
            self.hp_b = Helsepersonell.objects.create(name='Lege B')
            self.sted_b = Lokasjon.objects.create(navn='Scene B')
            self.vakt = opprett_vakt('Brannvakt', year=2026, startet=timezone.now())
        with transaction.atomic():
            gjor_aktiv(self.vakt)
        for slug, nivaa in (('patients', 'skriv_full'), ('oppdrag', 'skriv_leder'),
                            ('ko', 'skriv_leder')):
            gi_modultilgang(bruker=self.kari, modul_slug=slug, nivaa=nivaa, portal=self.brann)
        self.c = Client()
        self.c.force_login(self.kari)

    # ── Pasientregistreringen ──

    def test_registeret_er_portalens(self):
        navn = [r['name'] for r in self.c.get('/pasienter/api/helsepersonell/').json()]
        self.assertEqual(navn, ['Lege B'])

    def _admin(self):
        """Registeret skrives av global admin; hun står i Brann etter et valg."""
        from accounts.models import CustomUser
        sjef = CustomUser.objects.create_user(username='sjef', password='x', role='admin',
                                              must_change_password=False)
        c = Client(headers={'X-Portal': 'brann'})
        c.force_login(sjef)
        c.post('/portal/', {'portal': 'brann'})
        return c

    def test_en_rad_fra_en_annen_portal_kan_ikke_endres(self):
        self.c = self._admin()
        svar = self.c.put(f'/pasienter/api/helsepersonell/{self.hp_s.pk}/',
                          content_type='application/json', data={'name': 'Kapret'})
        self.assertEqual(svar.status_code, 404)
        svar = self.c.put(f'/pasienter/api/helsepersonell/{self.hp_b.pk}/',
                          content_type='application/json', data={'name': 'Lege B2'})
        self.assertEqual(svar.status_code, 200, svar.content)

    def test_samme_navn_i_en_annen_portal_er_lov(self):
        from patients.models import Helsepersonell
        self.c = self._admin()
        svar = self.c.post('/pasienter/api/helsepersonell/', content_type='application/json',
                           data={'name': 'Lege S'})
        self.assertEqual(svar.status_code, 201, svar.content)
        self.assertEqual(Helsepersonell.objects.get(pk=svar.json()['id']).portal, self.brann)
        svar = self.c.post('/pasienter/api/helsepersonell/', content_type='application/json',
                           data={'name': 'Lege B'})
        self.assertEqual(svar.status_code, 400)

    def _pasient(self, **data):
        import json
        data = {'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00', **data}
        return self.c.post('/pasienter/api/patients/', data=json.dumps(data),
                           content_type='application/json')

    def test_pasienten_faar_ikke_en_forstehjelper_fra_en_annen_portal(self):
        self.assertEqual(self._pasient(forstehjelper=self.fh_s.pk).status_code, 400)
        self.assertEqual(self._pasient(forstehjelper=self.fh_b.pk).status_code, 201)

    def test_mine_pasienter_er_raden_i_portalen(self):
        svar = self.c.get('/pasienter/')
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(svar.context['mitt_forstehjelper_id'], self.fh_b.pk)

    def test_kontokoblingen_roerer_bare_portalen(self):
        from core.portal import aktiver_portal
        from patients.kontokobling import PasientRolleForm
        with aktiver_portal(self.brann):
            skjema = PasientRolleForm(self.kari, data={'pasient_rolle': 'helsepersonell'})
            self.assertTrue(skjema.is_valid(), skjema.errors)
            skjema.save()
        self.fh_s.refresh_from_db()
        self.fh_b.refresh_from_db()
        self.assertEqual(self.fh_s.user, self.kari, 'Standard skal stå urørt')
        self.assertIsNone(self.fh_b.user)
        with aktiver_portal(self.standard):
            self.assertEqual(PasientRolleForm(self.kari).fields['pasient_rolle'].initial,
                             'forstehjelper')

    def test_mitt_helsepersonell_er_raden_i_portalen(self):
        """Koblet bare i Standard: i Brann er hun ingen. (Med rader i begge avgjorde
        databasens rekkefølge utfallet, og mutanten overlevde.)"""
        self.hp_s.user = self.kari
        self.hp_s.save()
        self.assertIsNone(self.c.get('/pasienter/').context['mitt_helsepersonell_id'])
        self.hp_b.user = self.kari
        self.hp_b.save()
        self.assertEqual(self.c.get('/pasienter/').context['mitt_helsepersonell_id'], self.hp_b.pk)

    # Kontokoblingen: én test per oppslag (mutantene 15–20 overlevde første runde —
    # testen over gikk bare gjennom den ene `update`).

    def _rolle_i(self, portal):
        from core.portal import aktiver_portal
        from patients.kontokobling import PasientRolleForm
        with aktiver_portal(portal):
            return PasientRolleForm(self.kari).fields['pasient_rolle'].initial

    def _lagre_i(self, portal, rolle):
        from core.portal import aktiver_portal
        from patients.kontokobling import PasientRolleForm
        with aktiver_portal(portal):
            skjema = PasientRolleForm(self.kari, data={'pasient_rolle': rolle})
            self.assertTrue(skjema.is_valid(), skjema.errors)
            skjema.save()

    def test_rollen_som_vises_er_portalens(self):
        self.fh_b.user = None
        self.fh_b.save()
        self.hp_b.user = self.kari
        self.hp_b.save()
        self.assertEqual(self._rolle_i(self.brann), 'helsepersonell')

    def test_helsepersonell_i_en_annen_portal_gir_ingen_rolle_her(self):
        self.fh_s.user = None
        self.fh_s.save()
        self.fh_b.user = None
        self.fh_b.save()
        self.hp_s.user = self.kari
        self.hp_s.save()
        self.assertEqual(self._rolle_i(self.brann), 'ingen')

    def test_helsepersonell_i_en_annen_portal_kobles_ikke_fra(self):
        self.hp_s.user = self.kari
        self.hp_s.save()
        self._lagre_i(self.brann, 'forstehjelper')
        self.hp_s.refresh_from_db()
        self.assertEqual(self.hp_s.user, self.kari)

    def test_raden_med_brukernavnet_hentes_i_portalen(self):
        from patients.models import Forstehjelper, Helsepersonell
        from core.portal import aktiver_portal
        with aktiver_portal(self.standard):
            fh = Forstehjelper.objects.create(name='kari')
            hp = Helsepersonell.objects.create(name='kari')
        for rolle, rad in (('forstehjelper', fh), ('helsepersonell', hp)):
            with self.subTest(rolle=rolle):
                self._lagre_i(self.brann, rolle)
                rad.refresh_from_db()
                self.assertIsNone(rad.user, 'Standards rad skal ikke tas')
                modell = type(rad)
                self.assertEqual(modell.objects.get(portal=self.brann, user=self.kari).name, 'kari')

    # ── Lokasjonene ──

    def test_valglista_er_portalens(self):
        data = self.c.get('/oppdrag/api/lokasjoner/').json()['data']
        self.assertEqual([r['navn'] for r in data], ['Scene B'])

    def test_en_lokasjon_fra_en_annen_portal_kan_ikke_endres(self):
        svar = self.c.put(f'/oppdrag/api/lokasjoner/{self.sted_s.pk}/',
                          content_type='application/json', data={'navn': 'Kapret'})
        self.assertEqual(svar.status_code, 404)

    def test_samme_stedsnavn_i_en_annen_portal_er_lov(self):
        svar = self.c.post('/oppdrag/api/lokasjoner/', content_type='application/json',
                           data={'navn': 'Scene S'})
        self.assertIn(svar.status_code, (200, 201), svar.content)
        svar = self.c.post('/oppdrag/api/lokasjoner/', content_type='application/json',
                           data={'navn': 'Scene B'})
        self.assertEqual(svar.status_code, 400)

    def test_omsorteringen_tar_ikke_en_annen_portals_rad(self):
        svar = self.c.put('/oppdrag/api/lokasjoner/rekkefolge/', content_type='application/json',
                          data={'ider': [self.sted_b.pk, self.sted_s.pk]})
        self.assertEqual(svar.status_code, 400)

    def _oppdrag(self, sted):
        return self.c.post('/oppdrag/api/oppdrag/', content_type='application/json',
                           data={'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt',
                                 'lokasjon_id': sted.pk, 'enhet_ider': []})

    def test_oppdraget_faar_ikke_en_lokasjon_fra_en_annen_portal(self):
        self.assertEqual(self._oppdrag(self.sted_s).status_code, 400)
        self.assertEqual(self._oppdrag(self.sted_b).status_code, 200)

    def test_oppdraget_flyttes_ikke_til_en_annen_portals_lokasjon(self):
        oppdrag_id = self._oppdrag(self.sted_b).json()['data']['id']
        svar = self.c.put(f'/oppdrag/api/oppdrag/{oppdrag_id}/', content_type='application/json',
                          data={'lokasjon_id': self.sted_s.pk})
        self.assertEqual(svar.status_code, 400)

    def test_ko_hendelsens_lokasjon(self):
        from core.portal import aktiver_portal
        from ko.views_hendelser import _lokasjon_fra
        with aktiver_portal(self.brann):
            self.assertEqual(_lokasjon_fra({'lokasjon_id': self.sted_s.pk}),
                             (None, 'Ukjent lokasjon.'))
            self.assertEqual(_lokasjon_fra({'lokasjon_id': self.sted_b.pk}), (self.sted_b, None))

    def test_ko_tavlas_rader_og_oppsett(self):
        from core.portal import aktiver_portal
        from ko import tavle
        from ko.services import Ugyldig
        with aktiver_portal(self.brann):
            rader = [r['navn'] for r in tavle.tavle_data(self.vakt)['rader']]
            self.assertEqual(rader, ['Scene B'])
            with self.assertRaises(Ugyldig):
                tavle.lagre_oppsett(skjulte_ider=[self.sted_s.pk], fulgte_ider=[])
            tavle.lagre_oppsett(skjulte_ider=[self.sted_b.pk], fulgte_ider=[])

    def test_ko_tavlas_innstillinger(self):
        data = self.c.get('/ko/api/tavle/oppsett/').json()['data']
        self.assertEqual([r['navn'] for r in data['lokasjoner']], ['Scene B'])

    def _tavlekall(self, sti, kropp):
        from types import SimpleNamespace
        from unittest import mock
        fake = SimpleNamespace(pk=1)
        with mock.patch('ko.views_tavle._tavle_gate', return_value=None), \
                mock.patch('ko.views_tavle._tavle_ressurs', return_value=fake), \
                mock.patch('ko.tavle.plasser', return_value=fake), \
                mock.patch('ko.tavle.planlegg_pause', return_value=fake), \
                mock.patch('ko.views_tavle._tavle_tid', return_value=None):
            return self.c.post(sti, content_type='application/json', data=kropp)

    def test_ko_plassering_paa_en_annen_portals_lokasjon(self):
        sti = '/ko/api/tavle/plasser/'
        self.assertEqual(self._tavlekall(sti, {'lokasjon_id': self.sted_s.pk}).status_code, 404)
        self.assertEqual(self._tavlekall(sti, {'lokasjon_id': self.sted_b.pk}).status_code, 200)

    def test_ko_planlagt_plassering_paa_en_annen_portals_lokasjon(self):
        sti = '/ko/api/tavle/pauser/'
        self.assertEqual(self._tavlekall(sti, {'lokasjon_id': self.sted_s.pk}).status_code, 404)
        self.assertEqual(self._tavlekall(sti, {'lokasjon_id': self.sted_b.pk}).status_code, 200)

    def test_ko_programmets_steder(self):
        from datetime import timedelta

        from django.utils import timezone

        from core.portal import aktiver_portal
        from ko import program
        from ko.services import Ugyldig
        fra = timezone.now() + timedelta(hours=1)
        with aktiver_portal(self.brann):
            self.assertEqual([s['navn'] for s in program.program_data(self.vakt)['steder']],
                             ['Scene B'])
            with self.assertRaisesMessage(Ugyldig, 'Ukjent sted'):
                program.lagre_post(self.vakt, {'navn': 'X', 'lokasjon_id': self.sted_s.pk},
                                   fra=fra, til=fra + timedelta(hours=1), bruker=self.kari)
            program.lagre_post(self.vakt, {'navn': 'X', 'lokasjon_id': self.sted_b.pk},
                               fra=fra, til=fra + timedelta(hours=1), bruker=self.kari)

    def test_ko_kopierer_ikke_til_en_annen_portals_sted(self):
        """Stedet finnes på id, ellers på navnet — begge i portalen (mutantene 3 og 4)."""
        from datetime import date, timedelta

        from django.utils import timezone

        from core.portal import aktiver_portal
        from core.vakt import opprett_vakt
        from ko import program
        from ko.models import Programpost
        with aktiver_portal(self.brann):
            fjor = opprett_vakt('Fjorår', year=2025, startet=timezone.now() - timedelta(days=365))
        fra = timezone.now() - timedelta(days=365)
        Programpost.objects.create(vakt=fjor, lokasjon=self.sted_s, lokasjon_navn='Scene S',
                                   navn='Band', fra=fra, til=fra + timedelta(hours=1))
        with aktiver_portal(self.brann):
            svar = program.kopier_program(fjor, self.vakt, bruker=self.kari,
                                          forste_dogn=date.today() + timedelta(days=1))
        self.assertEqual(svar['kopiert'], 0, svar)
        # Motprøve: med portalens eget sted går den samme konserten gjennom.
        Programpost.objects.filter(vakt=fjor).update(lokasjon=self.sted_b, lokasjon_navn='Scene B')
        with aktiver_portal(self.brann):
            svar = program.kopier_program(fjor, self.vakt, bruker=self.kari,
                                          forste_dogn=date.today() + timedelta(days=1))
        self.assertEqual(svar['kopiert'], 1, svar)

    def test_park_stedene(self):
        from core.portal import aktiver_portal
        from park import services
        with aktiver_portal(self.brann):
            self.assertEqual([s.navn for s in services.steder()], ['Scene B'])
            self.assertEqual([s['navn'] for s in services.alle_steder_med_synlighet()],
                             ['Scene B'])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KoOgParkTests(TestCase):
    """Fase 4c: KOs lister og ansvarsmerket per portal, og parklenken som bærer
    portalen inn på en side uten innlogging (§4.12, §4.13)."""

    def setUp(self):
        from django.core.cache import cache
        from django.db import transaction
        from django.utils import timezone

        from accounts.models import CustomUser
        from accounts.test_helpers import gi_modultilgang
        from core.models import ModuleSettings, Vaktportal
        from core.portal import aktiver_portal, eneste_portal
        from core.vakt import gjor_aktiv, opprett_vakt
        from ko.models import Ansvarsomraade, Kjennetegn, Konserttype
        from oppdrag.models import Lokasjon

        cache.clear()
        self.addCleanup(cache.clear)
        ModuleSettings.objects.update_or_create(slug='park', defaults={'enabled': True})
        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        with aktiver_portal(self.standard):
            self.samband_s = Ansvarsomraade.objects.create(navn='Samband S')
            self.artist_s = Konserttype.objects.create(navn='Artist S')
            self.pyro_s = Kjennetegn.objects.create(navn='Pyro S')
            self.sted_s = Lokasjon.objects.create(navn='Scene S')
        with aktiver_portal(self.brann):
            self.samband_b = Ansvarsomraade.objects.create(navn='Samband B')
            self.artist_b = Konserttype.objects.create(navn='Artist B')
            self.pyro_b = Kjennetegn.objects.create(navn='Pyro B')
            self.sted_b = Lokasjon.objects.create(navn='Scene B')
            self.vakt = opprett_vakt('Brannvakt', year=2026, startet=timezone.now())
        with transaction.atomic():
            gjor_aktiv(self.vakt)
        self.kari = CustomUser.objects.create_user(username='kari', password='x',
                                                   must_change_password=False)
        gi_modultilgang(bruker=self.kari, modul_slug='ko', nivaa='skriv_leder', portal=self.brann)
        self.c = Client()
        self.c.force_login(self.kari)

    # ── KO ──

    def test_listene_er_portalens(self):
        for sti, navn in (('ansvarsomraader', 'Samband B'), ('konserttyper', 'Artist B'),
                          ('kjennetegn', 'Pyro B')):
            with self.subTest(sti=sti):
                data = self.c.get(f'/ko/api/{sti}/').json()['data']
                self.assertEqual([r['navn'] for r in data], [navn])

    def test_ansvarsomraadene_operatoren_velger_mellom(self):
        from core.portal import aktiver_portal
        from ko import services
        with aktiver_portal(self.brann):
            self.assertEqual(services.ansvarsomraader_aktive(), ['Samband B'])

    def test_ansvar_fra_en_annen_portal_avvises(self):
        svar = self.c.post('/ko/api/ansvar/', content_type='application/json',
                           data={'omraade': 'Samband S'})
        self.assertEqual(svar.status_code, 400)
        svar = self.c.post('/ko/api/ansvar/', content_type='application/json',
                           data={'omraade': 'Samband B'})
        self.assertEqual(svar.status_code, 200, svar.content)

    def test_ansvarsmerket_er_per_portal(self):
        """Samme person kan ha samband i Brann og ressurser i Standard."""
        from core.portal import aktiver_portal
        from ko import services
        from ko.models import Ansvarsmerke
        with aktiver_portal(self.standard):
            services.sett_ansvar(self.kari, 'Samband S')
        with aktiver_portal(self.brann):
            self.assertEqual(services.ansvar_for(self.kari), '')
            services.sett_ansvar(self.kari, 'Samband B')
            self.assertEqual(services.ansvar_for(self.kari), 'Samband B')
        with aktiver_portal(self.standard):
            self.assertEqual(services.ansvar_for(self.kari), 'Samband S')
        self.assertEqual(Ansvarsmerke.objects.filter(bruker=self.kari).count(), 2)

    def test_linja_stemples_med_merket_i_vaktas_portal(self):
        """`skriv_linje` har vakta, og tar portalen derfra — ikke fra konteksten."""
        from core.portal import aktiver_portal
        from ko import services
        with aktiver_portal(self.standard):
            services.sett_ansvar(self.kari, 'Samband S')
        with aktiver_portal(self.brann):
            services.sett_ansvar(self.kari, 'Samband B')
        with aktiver_portal(self.standard):
            linje = services.skriv_linje(self.vakt, 'Hei', bruker=self.kari)
        self.assertEqual(linje.ansvarsomraade, 'Samband B')

    def test_tilstede_viser_merket_i_portalen(self):
        """«Hvem har KO oppe» i Brann viser Brann-merket, ikke Standards."""
        from core.portal import aktiver_portal
        from ko import services
        with aktiver_portal(self.standard):
            services.sett_ansvar(self.kari, 'Samband S')
        self.c.get('/ko/')   # en sesjon med KO oppe

        def kari():
            rader = self.c.get('/ko/api/tilstede/').json()['data']
            return [r['ansvar'] for r in rader if r['brukernavn'] == 'kari']
        self.assertEqual(kari(), [''])
        with aktiver_portal(self.brann):
            services.sett_ansvar(self.kari, 'Samband B')
        self.assertEqual(kari(), ['Samband B'])

    def test_programmet_tar_ikke_artist_eller_kjennetegn_fra_en_annen_portal(self):
        from datetime import timedelta

        from django.utils import timezone

        from core.portal import aktiver_portal
        from ko import program
        from ko.services import Ugyldig
        fra = timezone.now() + timedelta(hours=1)

        def lagre(**data):
            program.lagre_post(self.vakt, {'navn': 'X', 'lokasjon_id': self.sted_b.pk, **data},
                               fra=fra, til=fra + timedelta(hours=1), bruker=self.kari)
        with aktiver_portal(self.brann):
            with self.assertRaisesMessage(Ugyldig, 'Ukjent konserttype'):
                lagre(konserttype_id=self.artist_s.pk)
            with self.assertRaisesMessage(Ugyldig, 'Ukjent kjennetegn'):
                lagre(kjennetegn=[self.pyro_s.pk])
            lagre(konserttype_id=self.artist_b.pk, kjennetegn=[self.pyro_b.pk])
            data = program.program_data(self.vakt)
        self.assertEqual([t['navn'] for t in data['konserttyper']], ['Artist B'])
        self.assertEqual([k['navn'] for k in data['kjennetegn']], ['Pyro B'])

    def test_i_bruk_teller_bare_portalens_merker(self):
        from core.portal import aktiver_portal
        from ko.models import Ansvarsmerke, Ansvarsomraade
        with aktiver_portal(self.standard):
            Ansvarsomraade.objects.create(navn='Felles')
            Ansvarsmerke.objects.create(bruker=self.kari, omraade='Felles')
        with aktiver_portal(self.brann):
            felles = Ansvarsomraade.objects.create(navn='Felles')
        # Sletting fra en verdiliste er global admin (`core.verdilister`).
        from accounts.models import CustomUser
        sjef = CustomUser.objects.create_user(username='sjef', password='x', role='admin',
                                              must_change_password=False)
        admin = Client(headers={'X-Portal': 'brann'})
        admin.force_login(sjef)
        admin.post('/portal/', {'portal': 'brann'})
        svar = admin.delete(f'/ko/api/ansvarsomraader/{felles.pk}/',
                            content_type='application/json', data={'confirm': True})
        self.assertEqual(svar.status_code, 200, svar.content)   # Standards merke teller ikke

    # ── Park ──

    def _lenke(self, portal):
        from datetime import timedelta

        from django.utils import timezone

        from core.portal import aktiver_portal
        from park import services
        naa = timezone.now()
        with aktiver_portal(portal):
            _, token = services.lag_lenke(navn=f'Kort {portal.slug}', aapen_fra=naa,
                                          aapen_til=naa + timedelta(hours=2))
        return token

    def _oppsett(self, token):
        import uuid
        return Client().get('/lag/r/api/oppsett/', HTTP_X_PARK_LENKE=token,
                            HTTP_X_PARK_TELEFON=str(uuid.uuid4()))

    def test_lenken_baerer_portalen_inn_paa_siden_uten_innlogging(self):
        svar = self._oppsett(self._lenke(self.brann))
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertEqual(svar.json()['vakt'], 'Brannvakt')
        self.assertEqual([s['navn'] for s in svar.json()['steder']], ['Scene B'])

    def test_en_lenke_i_en_annen_portal_ser_den_portalen(self):
        """Motprøven: samme side, en Standard-lenke, og ingenting fra Brann."""
        svar = self._oppsett(self._lenke(self.standard))
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertNotEqual(svar.json()['vakt'], 'Brannvakt')
        self.assertEqual([s['navn'] for s in svar.json()['steder']], ['Scene S'])

    def test_lenkelista_og_fjerningen_er_portalens(self):
        from accounts.test_helpers import gi_modultilgang
        from park.models import Parklenke
        gi_modultilgang(bruker=self.kari, modul_slug='park', nivaa='skriv_leder', portal=self.brann)
        self._lenke(self.standard)
        self._lenke(self.brann)
        navn = [r['navn'] for r in self.c.get('/lag/api/lenker/').json()['data']]
        self.assertEqual(navn, ['Kort brann'])
        standard = Parklenke.objects.get(navn='Kort standard')
        svar = self.c.post(f'/lag/api/lenker/{standard.pk}/fjern/',
                           content_type='application/json', data={'confirm': True})
        self.assertEqual(svar.status_code, 404)
        brann = Parklenke.objects.get(navn='Kort brann')
        svar = self.c.post(f'/lag/api/lenker/{brann.pk}/fjern/',
                           content_type='application/json', data={'confirm': True})
        self.assertEqual(svar.status_code, 200)

    def test_et_sted_fra_en_annen_portal_skjules_ikke_herfra(self):
        from accounts.test_helpers import gi_modultilgang
        gi_modultilgang(bruker=self.kari, modul_slug='park', nivaa='skriv_leder', portal=self.brann)
        for sted, ventet in ((self.sted_s, 404), (self.sted_b, 200)):
            svar = self.c.post(f'/lag/api/steder/{sted.pk}/skjul/',
                               content_type='application/json', data={'skjult': True})
            self.assertEqual(svar.status_code, ventet, sted.navn)

    def test_en_registrering_fra_en_annen_portal_slettes_ikke_herfra(self):
        import uuid

        from accounts.test_helpers import gi_modultilgang
        from core.vakt import hent_aktiv_vakt
        from park.models import Parklenke, Registrering
        gi_modultilgang(bruker=self.kari, modul_slug='park', nivaa='skriv_leder', portal=self.brann)
        self._lenke(self.standard)
        self._lenke(self.brann)

        def rad(portal, navn):
            return Registrering.objects.create(
                vakt=hent_aktiv_vakt(portal), lenke=Parklenke.objects.get(portal=portal),
                ressurs_navn='Lag 1', problemstilling='Skrubbsår', utfall='Behandlet',
                lokasjon_navn=navn, idempotency_key=str(uuid.uuid4()))
        for registrering, ventet in ((rad(self.standard, 'S'), 404), (rad(self.brann, 'B'), 200)):
            svar = self.c.post(f'/lag/api/registreringer/{registrering.pk}/slett/',
                               content_type='application/json', data={'grunn': 'Feil lag'})
            self.assertEqual(svar.status_code, ventet, svar.content)

    def test_slett_etter_paa_en_annen_portals_lenke(self):
        from accounts.test_helpers import gi_modultilgang
        from django.utils import timezone

        from park.models import Parklenke
        gi_modultilgang(bruker=self.kari, modul_slug='park', nivaa='skriv_leder', portal=self.brann)
        self._lenke(self.standard)
        self._lenke(self.brann)
        for portal, ventet in ((self.standard, 404), (self.brann, 409)):
            lenke = Parklenke.objects.get(portal=portal)
            svar = self.c.post(f'/lag/api/lenker/{lenke.pk}/slett-etter/',
                               content_type='application/json',
                               data={'etter': timezone.now().isoformat()})
            self.assertEqual(svar.status_code, ventet, svar.content)
