"""Tilgangsmodellen — fase 3.

Egen fil fordi den svarer på et annet spørsmål enn `tests_oppsett.py` og
`tests_registre.py`: de tester hva endepunktene *gjør*, denne tester hvem som
slipper inn på dem. De to endres av ulike grunner, og en fil som blander dem
blir rød av begge.

**Fire kontoer går gjennom hele matrisen.** Det er poenget med fila: hver
regel prøves fra alle fire sidene, ikke bare fra den som skal slippe inn. En
tilgangstest som bare beviser at den rette kommer inn, beviser ingenting om
hvem som holdes ute.

| Konto | Har |
|---|---|
| `leser` | `les` |
| `kb` | `skriv_handling` + mannskapsrad i Haugesund (badgen) |
| `vaktleder` | `skriv_full`, ingen badge |
| `admin` | global admin |

De to reglene som bærer fasen:

1. **Den doble regelen** (§4.2) — badgen på personen *og* reservasjonen på
   ressursen. En ureservert ressurs er ikke et fristed.
2. **To felter er unntatt badgen** — `korps_id` og `user_id` handler ikke om
   personen, men om hvem som rår over henne.
"""
from datetime import timedelta

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.modules import get_module

from . import services
from .models import Kompetanse, Korps, Mannskap, Ressurs, Vaktpost
from .test_helpers import KO, LAG, gruppe, lag_ressurs, lag_rolle


def _bruker(navn, nivaa=None, *, admin=False):
    b = CustomUser.objects.create_user(
        username=navn, password='x', role='admin' if admin else 'bruker',
        must_change_password=False)
    if nivaa:
        ModulTilgang.objects.create(bruker=b, modul_slug='vaktliste', nivaa=nivaa)
    return b


def _klient(bruker):
    c = Client()
    c.force_login(bruker)
    return c


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TilgangsBasis(TestCase):
    """De fire kontoene, to korps, og et oppsett å bryne dem på."""

    def setUp(self):
        self.hgsd = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        self.karmoy = Korps.objects.create(navn='Karmøy')
        self.rolle = lag_rolle('Lagleder')
        self.komp = Kompetanse.objects.create(navn='Sykepleier')

        self.vl = services.opprett_planlagt_vakt('Vakta')
        self.res_hgsd = lag_ressurs(
            vaktliste=self.vl, navn='Lag HGSD', gruppe=gruppe(LAG), korps=self.hgsd)
        self.res_karmoy = lag_ressurs(
            vaktliste=self.vl, navn='Lag Karmøy', gruppe=gruppe(LAG),
            korps=self.karmoy)
        self.res_fri = lag_ressurs(
            vaktliste=self.vl, navn='KO', gruppe=gruppe(KO))

        self.p_hgsd = Mannskap.objects.create(navn='Kari', korps=self.hgsd)
        self.p_karmoy = Mannskap.objects.create(navn='Ola', korps=self.karmoy)

        self.leser = _bruker('leser', 'les')
        self.korpsbruker = _bruker('kb', 'skriv_handling')
        self.p_hgsd.user = self.korpsbruker
        self.p_hgsd.save()
        self.vaktleder = _bruker('vl', 'skriv_full')
        # `skriv_leder` kom 30. aug. 2026 og er trinnet over: den som *setter
        # opp* vakta framfor den som bemanner den.
        self.leder = _bruker('leder', 'skriv_leder')
        self.admin = _bruker('adm', admin=True)

        self.c_leser = _klient(self.leser)
        self.c_kb = _klient(self.korpsbruker)
        self.c_vl = _klient(self.vaktleder)
        self.c_leder = _klient(self.leder)
        self.c_adm = _klient(self.admin)
        self.na = timezone.now()

    def _iso(self, timer=0):
        return (self.na + timedelta(hours=timer)).isoformat()

    def _sett_paa(self, klient, ressurs, mannskap, **overstyr):
        kropp = {'mannskap_id': mannskap.pk, 'fra_tid': self._iso(0),
                 'til_tid': self._iso(8)}
        kropp.update(overstyr)
        return klient.post(f'/vaktliste/api/ressurser/{ressurs.pk}/vaktposter/',
                           data=kropp, content_type='application/json')


class SidetilgangTests(TilgangsBasis):
    """`les` slipper inn på begge sidene. Fase 2 slapp bare admin inn."""

    def test_alle_med_nivaa_naar_begge_sidene(self):
        for navn, c in (('les', self.c_leser), ('skriv_handling', self.c_kb),
                        ('skriv_full', self.c_vl), ('admin', self.c_adm)):
            for sti in ('/vaktliste/', '/vaktliste/registre/'):
                with self.subTest(konto=navn, sti=sti):
                    self.assertEqual(c.get(sti).status_code, 200)

    def test_uten_rad_er_begge_stengt(self):
        c = _klient(_bruker('utenfor'))
        for sti in ('/vaktliste/', '/vaktliste/registre/'):
            with self.subTest(sti=sti):
                self.assertEqual(c.get(sti).status_code, 403)

    def test_siden_sender_nivaa_og_badge_til_nettleseren(self):
        """Grensesnittet gater på `window.MODUL_TILGANG`, ikke på rollen —
        ellers viser vi knapper som fører til 403."""
        res = self.c_kb.get('/vaktliste/')
        self.assertContains(res, 'skriv_handling')
        self.assertContains(res, f'window.MITT_KORPS_ID = {self.hgsd.pk}')

    def test_konto_uten_badge_faar_null(self):
        res = self.c_vl.get('/vaktliste/')
        self.assertContains(res, 'window.MITT_KORPS_ID = null')


class LesingTests(TilgangsBasis):
    """`les` ser **hele** lista, alle korps (§4.4).

    Poenget med en vaktliste er samordning på tvers av korps. Den som ikke
    skal se andre korps, skal ikke ha modulen.
    """

    def test_leser_ser_alle_korps_sine_ressurser(self):
        data = self.c_leser.get(
            f'/vaktliste/api/vaktlister/{self.vl.pk}/').json()['data']
        self.assertEqual(len(data['ressurser']), 3)

    def test_korpsbruker_ser_ogsaa_andre_korps(self):
        data = self.c_kb.get('/vaktliste/api/mannskap/').json()['data']
        self.assertEqual({m['navn'] for m in data['mannskap']}, {'Kari', 'Ola'})

    def test_kontolista_er_bare_for_dem_som_kan_bruke_den(self):
        """`user_id` er `skriv_full`-felt. En liste over portalens brukernavn
        er ikke noe en korps-fører trenger for å føre lista si."""
        self.assertEqual(
            self.c_kb.get('/vaktliste/api/mannskap/').json()['data']['kontoer'],
            [])
        self.assertTrue(
            self.c_vl.get('/vaktliste/api/mannskap/').json()['data']['kontoer'])


class UtdelingTests(TilgangsBasis):
    """To skrivende terskler, ikke én.

    **`skriv_full` bemanner, `skriv_leder` setter opp** (30. aug. 2026, Andrés
    bestilling). Skillet er hva slags skade en feil gjør: setter bemanneren
    feil person på feil plass, retter hun det tilbake; fjerner noen en ressurs,
    forsvinner bemanningen med den.
    """

    def test_bare_lederen_planlegger_ny_vakt(self):
        for navn, c, ventet in (('les', self.c_leser, 403),
                                ('skriv_handling', self.c_kb, 403),
                                ('skriv_full', self.c_vl, 403),
                                ('skriv_leder', self.c_leder, 201),
                                ('admin', self.c_adm, 201)):
            with self.subTest(konto=navn):
                res = c.post('/vaktliste/api/vaktlister/',
                             data={'navn': f'Vakt {navn}'},
                             content_type='application/json')
                self.assertEqual(res.status_code, ventet)

    def test_bare_lederen_legger_til_ressurs(self):
        """Reservasjonen settes av den som deler ut. Kunne korps-brukeren
        opprette ressurser, kunne hun tildele seg selv — og da er
        reservasjonen ikke en tildeling.

        Fra 30. aug. 2026 stopper det også `skriv_full`: hva vakta *består av*
        er vaktlederens beslutning, ikke bemannerens.
        """
        for navn, c, ventet in (('les', self.c_leser, 403),
                                ('skriv_handling', self.c_kb, 403),
                                ('skriv_full', self.c_vl, 403),
                                ('skriv_leder', self.c_leder, 201)):
            with self.subTest(konto=navn):
                res = c.post(
                    f'/vaktliste/api/vaktlister/{self.vl.pk}/ressurser/',
                    data={'navn': f'Lag {navn}', 'gruppe_id': gruppe(LAG).pk,
                          'korps_id': self.hgsd.pk},
                    content_type='application/json')
                self.assertEqual(res.status_code, ventet)

    def test_bemanneren_fjerner_ikke_en_ressurs(self):
        """CASCADE tar skiftene. Den som bemanner skal ikke kunne slette
        andres arbeid ved å rydde bort en fane."""
        res = self.c_vl.delete(f'/vaktliste/api/ressurser/{self.res_hgsd.pk}/',
                               data={'confirm': True},
                               content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.assertTrue(Ressurs.objects.filter(pk=self.res_hgsd.pk).exists())

    def test_lederen_fjerner_en_ressurs_med_bekreftelse(self):
        uten = self.c_leder.delete(
            f'/vaktliste/api/ressurser/{self.res_hgsd.pk}/')
        self.assertEqual(uten.status_code, 400, 'bekreftelse mangler')
        self.assertTrue(Ressurs.objects.filter(pk=self.res_hgsd.pk).exists())

        med = self.c_leder.delete(
            f'/vaktliste/api/ressurser/{self.res_hgsd.pk}/',
            data={'confirm': True}, content_type='application/json')
        self.assertEqual(med.status_code, 200)
        self.assertFalse(Ressurs.objects.filter(pk=self.res_hgsd.pk).exists())

    def test_bemanneren_endrer_ikke_vaktas_lengde(self):
        """Spennet er grunnlaget kurven tegnes over, og et skift som faller
        utenfor et flyttet spenn er ikke noe bemanneren kan se komme."""
        res = self.c_vl.put(f'/vaktliste/api/vaktlister/{self.vl.pk}/',
                            data={'planlagt_slutt': self._iso(12)},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(
            self.c_leder.put(f'/vaktliste/api/vaktlister/{self.vl.pk}/',
                             data={'planlagt_slutt': self._iso(12)},
                             content_type='application/json').status_code, 200)

    def test_bemanneren_beholder_det_hun_skal_ha(self):
        """Nivået mistet oppsettet, ikke bemanningen — og heller ikke
        utskriften, som er hele grunnen til at hun ser lista."""
        self.assertEqual(
            self._sett_paa(self.c_vl, self.res_karmoy, self.p_karmoy).status_code,
            201, 'bemanner på tvers av korps som før')
        self.assertEqual(
            self.c_vl.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/').status_code,
            200, 'leser hele oppsettet — utskriftslista bygges av det')

    def test_korpsbruker_kan_ikke_fjerne_sin_egen_ressurs(self):
        """Hun bemanner den — hun eier den ikke."""
        res = self.c_kb.delete(f'/vaktliste/api/ressurser/{self.res_hgsd.pk}/')
        self.assertEqual(res.status_code, 403)
        self.assertTrue(Ressurs.objects.filter(pk=self.res_hgsd.pk).exists())

    def test_korpsbruker_kan_ikke_omreservere_en_ressurs(self):
        """Den korteste veien rundt hele regelen: sett `korps` på KO til
        mitt eget, og bemann den etterpå."""
        res = self.c_kb.put(
            f'/vaktliste/api/ressurser/{self.res_fri.pk}/',
            data={'korps_id': self.hgsd.pk}, content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.res_fri.refresh_from_db()
        self.assertIsNone(self.res_fri.korps_id)

    def test_verdimengdene_er_skriv_full(self):
        """Kunne korps-brukeren opprette korps, kunne hun lage seg et nytt
        å føre — og badgen hennes ville sluttet å avgrense noe.

        Rollene står ikke her: de er del av vaktoppsettet og krever
        `skriv_leder`. Se `RollerErGruppasTests` i `tests_registre.py`.
        """
        for sti in ('korps', 'kompetanser'):
            with self.subTest(sti=sti):
                self.assertEqual(
                    self.c_kb.post(f'/vaktliste/api/{sti}/', data={'navn': 'Nytt'},
                                   content_type='application/json').status_code,
                    403)
                self.assertEqual(
                    self.c_vl.post(f'/vaktliste/api/{sti}/', data={'navn': f'Ny {sti}'},
                                   content_type='application/json').status_code,
                    201)

    def test_verdimengdene_kan_leses_av_alle(self):
        """Nedtrekkslistene trenger dem — også korps-førerens."""
        for sti in ('korps', 'kompetanser', 'roller'):
            with self.subTest(sti=sti):
                self.assertEqual(
                    self.c_kb.get(f'/vaktliste/api/{sti}/').status_code, 200)

    def test_sletting_av_vaktliste_er_global_admin(self):
        """Irreversibelt: hele oppsettet og alle skiftene på det.

        Også `skriv_leder` stoppes. Lederen fjerner en ressurs, men å rive
        hele lista hører til samme kategori som resten av det irreversible i
        portalen — det er ikke en gradsforskjell fra å fjerne en bil.
        """
        for navn, c in (('skriv_full', self.c_vl), ('skriv_handling', self.c_kb),
                        ('skriv_leder', self.c_leder)):
            with self.subTest(konto=navn):
                res = c.delete(f'/vaktliste/api/vaktlister/{self.vl.pk}/',
                               data={'confirm': True},
                               content_type='application/json')
                self.assertEqual(res.status_code, 403)
        self.assertEqual(
            self.c_adm.delete(f'/vaktliste/api/vaktlister/{self.vl.pk}/',
                              data={'confirm': True},
                              content_type='application/json').status_code, 200)


class DobbelRegelTests(TilgangsBasis):
    """Badgen **og** reservasjonen, håndhevet på endepunktet (§4.2).

    Reglene er testet som funksjoner i `tests_oppsett.py`. Her prøves de der
    de faktisk står i veien for noen — gjennom HTTP.
    """

    def test_korpsbruker_bemanner_sin_egen_ressurs(self):
        res = self._sett_paa(self.c_kb, self.res_hgsd, self.p_hgsd)
        self.assertEqual(res.status_code, 201)

    def test_korpsbruker_nektes_annet_korps_sin_ressurs(self):
        res = self._sett_paa(self.c_kb, self.res_karmoy, self.p_hgsd)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Vaktpost.objects.count(), 0)

    def test_korpsbruker_nektes_annet_korps_sin_person(self):
        """Riktig ressurs er ikke nok — regelen er dobbel."""
        res = self._sett_paa(self.c_kb, self.res_hgsd, self.p_karmoy)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Vaktpost.objects.count(), 0)

    def test_ureservert_ressurs_er_stengt_for_korpsbrukeren(self):
        res = self._sett_paa(self.c_kb, self.res_fri, self.p_hgsd)
        self.assertEqual(res.status_code, 403)

    def test_leser_bemanner_ingenting(self):
        res = self._sett_paa(self.c_leser, self.res_hgsd, self.p_hgsd)
        self.assertEqual(res.status_code, 403)

    def test_skriv_full_blander_fritt(self):
        for ressurs in (self.res_hgsd, self.res_karmoy, self.res_fri):
            for person in (self.p_hgsd, self.p_karmoy):
                with self.subTest(ressurs=ressurs.navn, person=person.navn):
                    res = self._sett_paa(self.c_vl, ressurs, person)
                    self.assertEqual(res.status_code, 201)

    def test_korpsbruker_uten_badge_er_stengt(self):
        """Fail-closed: `skriv_handling` uten mannskapsrad har intet korps."""
        c = _klient(_bruker('uten_badge', 'skriv_handling'))
        self.assertEqual(
            self._sett_paa(c, self.res_hgsd, self.p_hgsd).status_code, 403)

    # ── Endring og fjerning av et eksisterende skift ──────────────────────
    def _vaktpost(self, ressurs, mannskap):
        return Vaktpost.objects.create(
            ressurs=ressurs, mannskap=mannskap,
            fra_tid=self.na, til_tid=self.na + timedelta(hours=8))

    def test_korpsbruker_endrer_sitt_eget_skift(self):
        vp = self._vaktpost(self.res_hgsd, self.p_hgsd)
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{vp.pk}/',
                            data={'til_tid': self._iso(12)},
                            content_type='application/json')
        self.assertEqual(res.status_code, 200)

    def test_korpsbruker_nektes_annet_korps_sitt_skift(self):
        """Regelen leses fra raden som *finnes*. Leste vi ressursen fra
        request-kroppen, kunne hun oppgitt sin egen og rørt hva som helst."""
        vp = self._vaktpost(self.res_karmoy, self.p_karmoy)
        for metode in ('put', 'delete'):
            with self.subTest(metode=metode):
                res = getattr(self.c_kb, metode)(
                    f'/vaktliste/api/vaktposter/{vp.pk}/',
                    data={'til_tid': self._iso(12)},
                    content_type='application/json')
                self.assertEqual(res.status_code, 403)
        self.assertTrue(Vaktpost.objects.filter(pk=vp.pk).exists())


class MannskapsregisterTilgangTests(TilgangsBasis):
    """Badgen på registersiden — og de to feltene som er unntatt den."""

    def test_korpsbruker_legger_til_i_sitt_eget_korps(self):
        res = self.c_kb.post('/vaktliste/api/mannskap/',
                             data={'navn': 'Nyansatt', 'korps_id': self.hgsd.pk},
                             content_type='application/json')
        self.assertEqual(res.status_code, 201)

    def test_korpsbruker_nektes_aa_legge_til_i_annet_korps(self):
        res = self.c_kb.post('/vaktliste/api/mannskap/',
                             data={'navn': 'Fremmed', 'korps_id': self.karmoy.pk},
                             content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.assertFalse(Mannskap.objects.filter(navn='Fremmed').exists())

    def test_leser_legger_ikke_til_noen(self):
        res = self.c_leser.post('/vaktliste/api/mannskap/',
                                data={'navn': 'Ny', 'korps_id': self.hgsd.pk},
                                content_type='application/json')
        self.assertEqual(res.status_code, 403)

    def test_korpsbruker_redigerer_sine_egne(self):
        res = self.c_kb.put(f'/vaktliste/api/mannskap/{self.p_hgsd.pk}/',
                            data={'telefon': '90000000',
                                  'kompetanse_ider': [self.komp.pk]},
                            content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['data']['telefon'], '90000000')

    def test_korpsbruker_nektes_andres(self):
        for metode in ('put', 'delete'):
            with self.subTest(metode=metode):
                res = getattr(self.c_kb, metode)(
                    f'/vaktliste/api/mannskap/{self.p_karmoy.pk}/',
                    data={'navn': 'Kapret'}, content_type='application/json')
                self.assertEqual(res.status_code, 403)
        self.p_karmoy.refresh_from_db()
        self.assertEqual(self.p_karmoy.navn, 'Ola')

    # ── De to unntatte feltene ────────────────────────────────────────────
    def test_korpsbruker_kan_ikke_flytte_noen_ut_av_korpset(self):
        """Flytting krever begge korps. Siden hun bare har ett, flytter hun
        ingen — og det er poenget: ellers kunne hun eksportert folk ut av
        rekkevidde, eller hentet andres inn."""
        res = self.c_kb.put(f'/vaktliste/api/mannskap/{self.p_hgsd.pk}/',
                            data={'korps_id': self.karmoy.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.p_hgsd.refresh_from_db()
        self.assertEqual(self.p_hgsd.korps_id, self.hgsd.pk)

    def test_korpsbruker_kan_ikke_hente_andres_inn(self):
        res = self.c_kb.put(f'/vaktliste/api/mannskap/{self.p_karmoy.pk}/',
                            data={'korps_id': self.hgsd.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)

    def test_skriv_full_flytter_fritt(self):
        res = self.c_vl.put(f'/vaktliste/api/mannskap/{self.p_karmoy.pk}/',
                            data={'korps_id': self.hgsd.pk},
                            content_type='application/json')
        self.assertEqual(res.json()['data']['korps_navn'], 'Haugesund')

    def test_korpsbruker_kan_ikke_koble_en_konto(self):
        """Koblingen flytter en badge: kontoen arver korpset, og dermed hva
        *den* kontoen får redigere."""
        offer = _bruker('offer')
        ny = Mannskap.objects.create(navn='Nyansatt', korps=self.hgsd)
        res = self.c_kb.put(f'/vaktliste/api/mannskap/{ny.pk}/',
                            data={'user_id': offer.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)
        ny.refresh_from_db()
        self.assertIsNone(ny.user_id)

    def test_korpsbruker_kan_ikke_koble_konto_ved_opprettelse(self):
        """Samme regel på veien inn — ellers er PUT-sperren bare en omvei."""
        offer = _bruker('offer2')
        res = self.c_kb.post('/vaktliste/api/mannskap/',
                             data={'navn': 'Ny', 'korps_id': self.hgsd.pk,
                                   'user_id': offer.pk},
                             content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.assertFalse(Mannskap.objects.filter(user=offer).exists())

    def test_skriv_full_kobler_konto(self):
        bruker = _bruker('koblet')
        ny = Mannskap.objects.create(navn='Nyansatt', korps=self.hgsd)
        res = self.c_vl.put(f'/vaktliste/api/mannskap/{ny.pk}/',
                            data={'user_id': bruker.pk},
                            content_type='application/json')
        self.assertEqual(res.json()['data']['brukernavn'], 'koblet')

    def test_korpsbruker_sletter_sin_egen_ubrukte(self):
        """Speilbildet av å legge inn. PROTECT stopper det uansett i det
        personen har gått en vakt."""
        ny = Mannskap.objects.create(navn='Feilført', korps=self.hgsd)
        self.assertEqual(
            self.c_kb.delete(f'/vaktliste/api/mannskap/{ny.pk}/').status_code, 200)


class NivaaEtikettTests(TestCase):
    """§4.5: samme nivå betyr ulike ting i ulike moduler.

    Uten en etikett per modul deles «Skrive: handling» ut i god tro med
    oppdragsmodulens betydning — og det er nøyaktig feilen rollemodellnotatet
    allerede har kalt ut én gang.
    """

    def test_de_to_modulene_kaller_samme_nivaa_ulike_ting(self):
        vaktliste = get_module('vaktliste').etikett_for('skriv_handling')
        oppdrag = get_module('oppdrag').etikett_for('skriv_handling')
        self.assertNotEqual(vaktliste, oppdrag)
        self.assertIn('korps', vaktliste.lower())
        self.assertIn('stempl', oppdrag.lower())

    def test_modul_uten_egen_etikett_faar_stigens(self):
        """Fallbacken skal være stigens generiske, ikke tomt."""
        self.assertEqual(get_module('statistikk').etikett_for('les'), 'Lese')

    def test_ukjent_nivaa_vises_raatt(self):
        """Udramatisk med vilje: dette er visning, ikke håndhevelse, og en
        ukjent verdi som vises rått er lettere å oppdage enn en tom."""
        self.assertEqual(get_module('oppdrag').etikett_for('finnes_ikke'),
                         'finnes_ikke')

    def test_matrisen_tilbyr_modulens_egen_etikett(self):
        from accounts.forms import ModulTilgangForm
        bruker = CustomUser.objects.create_user(
            username='m', password='x', must_change_password=False)
        skjema = ModulTilgangForm(bruker=bruker)
        valg = dict(skjema.fields['modul_vaktliste'].choices)
        self.assertEqual(valg['skriv_handling'], 'Skrive: eget korps')
        self.assertEqual(
            dict(skjema.fields['modul_oppdrag'].choices)['skriv_handling'],
            'Skrive: stempling')

    def test_matrisen_tilbyr_bare_modulens_egne_nivaaer(self):
        """Vernet fra før skal bestå: statistikk har ingen skriving."""
        from accounts.forms import ModulTilgangForm
        bruker = CustomUser.objects.create_user(
            username='m2', password='x', must_change_password=False)
        skjema = ModulTilgangForm(bruker=bruker)
        valg = dict(skjema.fields['modul_statistikk'].choices)
        self.assertNotIn('skriv_full', valg)
        self.assertNotIn('skriv_handling', valg)

    def test_min_profil_viser_samme_etikett_som_matrisen(self):
        """Kortet skal si det samme som skjemaet der tilgangen ble delt ut."""
        from core.views import modultilganger_for_visning
        bruker = CustomUser.objects.create_user(
            username='m3', password='x', must_change_password=False)
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='vaktliste', nivaa='skriv_handling')
        rader = {r['navn']: r['nivaa']
                 for r in modultilganger_for_visning(bruker)}
        self.assertEqual(rader['Vaktliste'], 'Skrive: eget korps')


class GrensesnittetsGatingTests(SimpleTestCase):
    """JS-en speiler serverens regler — og den speilingen må testes.

    Reglene står to steder med vilje: serveren håndhever, nettleseren tegner.
    Men to steder er to steder å ta feil, og et grensesnitt som viser «Sett på
    vakt» på en ressurs brukeren ikke får bemanne, gir en knapp som fører til
    en vegg — som er verre enn ingen knapp.

    Funnet ved mutasjonstesting: fjernet man reservasjonssjekken fra
    `kanBemanne()`, ble ingen test rød. Serveren stoppet fortsatt kallet, så
    hullet var kosmetisk — men det er nettopp den slags hull som overlever til
    noen stoler på grensesnittet.
    """

    def setUp(self):
        from patients.js_test_utils import (
            VAKTLISTE_JS, VAKTLISTE_REGISTRE_JS, build_harness, node_available)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.h_plan = build_harness((
            (VAKTLISTE_JS, ('_nivaa', '_erAdmin', 'kanSkriveAlt', 'kanLede',
                            'kanSkriveNoe', 'kanBemanne')),
        ))
        self.h_reg = build_harness((
            (VAKTLISTE_REGISTRE_JS, ('_nivaa', 'kanSkriveAlt',
                                     'kanRedigerePerson')),
        ))

    @staticmethod
    def _vindu(nivaa='', *, admin=False, korps='null'):
        """Stub av det malen setter. Node har ingen `window`."""
        return (
            f"globalThis.window = {{ MODUL_TILGANG: "
            f"{{ vaktliste: '{nivaa}', admin: {str(admin).lower()} }} }};\n"
            f"globalThis.window.MITT_KORPS_ID = {korps};\n"
        )

    def _kjor(self, harness, vindu, kode):
        from patients.js_test_utils import run_node
        return run_node(harness, vindu + kode)

    # ── Den doble regelens halvdel i nettleseren ─────────────────────────
    def test_korpsbruker_ser_bare_sine_egne_ressurser(self):
        self._kjor(self.h_plan, self._vindu('skriv_handling', korps=1), """
            assert(kanBemanne({korps_id: 1}) === true, 'egen ressurs');
            assert(kanBemanne({korps_id: 2}) === false, 'annet korps');
            assert(kanBemanne({korps_id: null}) === false,
                   'ureservert er ikke et fristed');
        """)

    def test_skriv_full_ser_alle(self):
        self._kjor(self.h_plan, self._vindu('skriv_full'), """
            assert(kanSkriveAlt() === true, 'skriv_full skriver alt');
            assert(kanBemanne({korps_id: null}) === true, 'ogsaa ureserverte');
            assert(kanBemanne({korps_id: 7}) === true, 'og andres');
        """)

    def test_bemanneren_ser_ikke_oppsettsknappene(self):
        """`skriv_full` bemanner, men setter ikke opp (30. aug. 2026).

        Knappene bak `kanLede()` er «Ny vaktliste», «Ny ressurs», «Rediger»,
        «Roller» og vaktas lengde. Serveren nekter uansett — men en knapp som
        fører til en vegg er verre enn ingen knapp.
        """
        self._kjor(self.h_plan, self._vindu('skriv_full'), """
            assert(kanSkriveAlt() === true, 'bemanner fortsatt alt');
            assert(kanLede() === false, 'men setter ikke opp vakta');
        """)

    def test_lederen_ser_alt_bemanneren_ser_og_mer(self):
        """Stigen er ordnet: `skriv_leder` inneholder `skriv_full`. Speiles
        det ikke i JS, mister lederen knappene bemanneren har."""
        self._kjor(self.h_plan, self._vindu('skriv_leder'), """
            assert(kanLede() === true, 'setter opp vakta');
            assert(kanSkriveAlt() === true, 'og bemanner alt bemanneren gjor');
            assert(kanBemanne({korps_id: 7}) === true, 'paa tvers av korps');
        """)

    def test_korpsbrukeren_leder_ingenting(self):
        self._kjor(self.h_plan, self._vindu('skriv_handling', korps=1), """
            assert(kanLede() === false, 'badgen fører et korps, ikke vakta');
        """)

    def test_admin_ser_alle_uten_nivaa(self):
        self._kjor(self.h_plan, self._vindu('', admin=True), """
            assert(kanSkriveAlt() === true, 'global admin staar utenfor');
            assert(kanLede() === true, 'ogsaa oppsettet');
            assert(kanBemanne({korps_id: 9}) === true, 'uansett reservasjon');
        """)

    def test_leser_ser_ingen_knapper(self):
        self._kjor(self.h_plan, self._vindu('les', korps=1), """
            assert(kanSkriveAlt() === false, 'les skriver ikke');
            assert(kanLede() === false, 'og setter ikke opp');
            assert(kanSkriveNoe() === false, 'heller ikke litt');
            assert(kanBemanne({korps_id: 1}) === false, 'selv med badge');
        """)

    def test_korpsbruker_uten_badge_ser_ingen_knapper(self):
        """Fail-closed, som på serveren: uten mannskapsrad intet korps."""
        self._kjor(self.h_plan, self._vindu('skriv_handling', korps='null'), """
            assert(kanBemanne({korps_id: 1}) === false, 'ingen badge, ingen knapp');
            assert(kanBemanne({korps_id: null}) === false, 'heller ikke ureservert');
        """)

    def test_tomt_vindu_gir_ingen_tilgang(self):
        """En side som ikke fikk satt `MODUL_TILGANG` skal vise minst mulig,
        ikke mest mulig."""
        self._kjor(self.h_plan, 'globalThis.window = {};\n', """
            assert(kanSkriveAlt() === false, 'tomt vindu skriver ikke');
            assert(kanBemanne({korps_id: 1}) === false, 'og bemanner ikke');
        """)

    # ── Badgen på registersiden ──────────────────────────────────────────
    def test_registersiden_folger_badgen(self):
        self._kjor(self.h_reg, self._vindu('skriv_handling', korps=1), """
            assert(kanRedigerePerson({korps_id: 1}) === true, 'egen');
            assert(kanRedigerePerson({korps_id: 2}) === false, 'andres');
        """)

    def test_registersiden_leser_redigerer_ingen(self):
        self._kjor(self.h_reg, self._vindu('les', korps=1), """
            assert(kanRedigerePerson({korps_id: 1}) === false, 'les redigerer ikke');
        """)


class LedigPlassTilgangTests(TilgangsBasis):
    """Å opprette et behov er å planlegge; å fylle det er å føre sitt korps.

    `mannskap=None` gir badge-halvdelen ingenting å sjekke mot, så regelen
    ville falt åpen på nøyaktig det tilfellet som er nytt. Derfor er en ledig
    plass eksplisitt `skriv_full`: vaktleder sier «Lag 1 trenger fire»,
    korpset fyller dem.
    """

    def _plass(self, klient, ressurs, **overstyr):
        kropp = {'fra_tid': self._iso(0), 'til_tid': self._iso(8)}
        kropp.update(overstyr)
        return klient.post(f'/vaktliste/api/ressurser/{ressurs.pk}/vaktposter/',
                           data=kropp, content_type='application/json')

    def test_korpsbruker_kan_ikke_opprette_ledige_plasser(self):
        """Hun bestemmer ikke hvor mange plasser laget hennes skal ha."""
        res = self._plass(self.c_kb, self.res_hgsd)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Vaktpost.objects.count(), 0)

    def test_skriv_full_oppretter_dem(self):
        self.assertEqual(
            self._plass(self.c_vl, self.res_hgsd).status_code, 201)

    def test_leser_oppretter_ingenting(self):
        self.assertEqual(
            self._plass(self.c_leser, self.res_hgsd).status_code, 403)

    def test_korpsbruker_fyller_plass_paa_sin_egen_ressurs(self):
        pk = self._plass(self.c_vl, self.res_hgsd).json()['data']['id']
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'mannskap_id': self.p_hgsd.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 200)

    def test_korpsbruker_kan_ikke_fylle_med_annet_korps(self):
        """Regelen sjekkes på nytt mot personen som skal **inn**. Uten det
        kunne hun fylt sin egen ressurs med en fra et annet korps."""
        pk = self._plass(self.c_vl, self.res_hgsd).json()['data']['id']
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'mannskap_id': self.p_karmoy.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.assertIsNone(Vaktpost.objects.get(pk=pk).mannskap_id)

    def test_korpsbruker_kan_ikke_fylle_plass_paa_annen_ressurs(self):
        pk = self._plass(self.c_vl, self.res_karmoy).json()['data']['id']
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'mannskap_id': self.p_hgsd.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)

    def test_korpsbruker_kan_ikke_tomme_en_plass_hun_ikke_raar_over(self):
        pk = self._plass(self.c_vl, self.res_karmoy,
                         mannskap_id=self.p_karmoy.pk).json()['data']['id']
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'mannskap_id': None},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)

    def test_korpsbruker_kan_ikke_avlyse_en_ledig_plass(self):
        """Hun fyller plasser, hun avlyser dem ikke — kunne hun det, ville et
        hull i bemanningen kunne skjules ved å slette raden som viste det."""
        pk = self._plass(self.c_vl, self.res_hgsd).json()['data']['id']
        res = self.c_kb.delete(f'/vaktliste/api/vaktposter/{pk}/')
        self.assertEqual(res.status_code, 403)
        self.assertTrue(Vaktpost.objects.filter(pk=pk).exists())

    def test_korpsbruker_kan_fjerne_sitt_eget_fylte_skift(self):
        """Å ta sin egen person av lista er noe annet enn å avlyse plassen."""
        pk = self._plass(self.c_vl, self.res_hgsd,
                         mannskap_id=self.p_hgsd.pk).json()['data']['id']
        self.assertEqual(
            self.c_kb.delete(f'/vaktliste/api/vaktposter/{pk}/').status_code, 200)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LedernivaaetsPlassIStigenTests(TestCase):
    """`skriv_leder` er fjerde trinn, og det er nytt for hele portalen.

    Et nytt trinn i `NIVAA_HIERARKI` er additivt for modulene som ikke
    deklarerer det — men bare hvis det faktisk ligger *over* `skriv_full` og
    bare hvis ingen andre moduler tilbyr det. Begge deler er lette å tro på
    uten å sjekke, og begge ville gitt tilgang ingen hadde bestemt.
    """

    def test_stigen_er_ordnet(self):
        from core.auth_decorators import har_tilgang
        bruker = _bruker('leder', 'skriv_leder')
        for krav in ('les', 'skriv_handling', 'skriv_full', 'skriv_leder'):
            with self.subTest(krav=krav):
                self.assertTrue(har_tilgang(bruker, 'vaktliste', krav))

    def test_skriv_full_naar_ikke_opp(self):
        from core.auth_decorators import har_tilgang
        bruker = _bruker('bemanner', 'skriv_full')
        self.assertTrue(har_tilgang(bruker, 'vaktliste', 'skriv_full'))
        self.assertFalse(har_tilgang(bruker, 'vaktliste', 'skriv_leder'))

    def test_bare_vaktlista_tilbyr_nivaaet(self):
        """Matrisen tilbyr de nivåene modulen deklarerer og ingen andre. Kom
        `skriv_leder` snikende inn på en annen modul, ville den fått et
        toppnivå ingen har definert hva betyr der."""
        from core.modules import get_all_modules
        for modul in get_all_modules():
            with self.subTest(modul=modul.slug):
                if modul.slug == 'vaktliste':
                    self.assertIn('skriv_leder', modul.nivaaer)
                else:
                    self.assertNotIn('skriv_leder', modul.nivaaer)

    def test_nivaaet_har_sin_egen_etikett(self):
        """«Skrive: leder» sier ikke hva lederen gjør. Etiketten må skille
        den fra «Skrive: alle korps» der den deles ut."""
        modul = get_module('vaktliste')
        leder = modul.etikett_for('skriv_leder')
        self.assertNotEqual(leder, modul.etikett_for('skriv_full'))
        self.assertIn('leder', leder.lower())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MalensGatingTests(TestCase):
    """Malen må merke oppsettsknappene med riktig klasse.

    JS-en skjuler `.vl-krev-leder` for alle under `skriv_leder`. Står en
    oppsettsknapp med `.vl-krev-full` i stedet, vises den for bemanneren og
    fører til en 403 — og en knapp som fører til en vegg er verre enn ingen
    knapp. Testen leser malen, fordi det er der feilen ville stått.
    """

    def _mal(self):
        from pathlib import Path
        from django.conf import settings
        return (Path(settings.BASE_DIR) / 'templates' / 'vaktliste'
                / 'index.html').read_text(encoding='utf-8')

    def test_oppsettsknappene_krever_leder(self):
        """«Ny vaktliste» står i malen og gates av klassen.

        «Ny ressurs» står *ikke* her: den bygges sist i fanerekka av
        `tegnFaner()`, som tegnes på nytt ved hvert panelbytte og derfor
        sjekker tilgangen selv. Se `NyRessursIFanerekkaTests`.
        """
        import re
        m = re.search(
            r'<button[^>]*data-bs-target="' + re.escape('#nyVaktlisteModal') + r'"',
            self._mal(), re.S)
        self.assertIsNotNone(m, 'fant ikke «Ny vaktliste»-knappen')
        self.assertIn('vl-krev-leder', m.group(0))

    def test_ny_ressurs_bygges_i_js_og_ikke_i_malen(self):
        """Står den begge steder, vises den to ganger — og den ene kopien
        gates av en klasse som ikke rekker over den andre."""
        self.assertNotIn('#nyRessursModal', self._mal().split('<div class="modal')[0])

    def test_vaktas_lengde_ligger_bak_ledergaten(self):
        self.assertIn('class="vl-krev-leder d-none"', self._mal())

    def test_utskriften_er_ikke_gatet(self):
        """Å skrive ut lista er hele grunnen til at bemanneren ser den."""
        import re
        m = re.search(r'<button[^>]*data-action="skrivUtVakta"[^>]*>',
                      self._mal(), re.S)
        self.assertIsNotNone(m)
        self.assertNotIn('vl-krev', m.group(0))

    def test_ingen_naken_fjern_ressurs_knapp(self):
        """Sletting skal bare finnes inne i «Rediger ressurs». Bygges den
        tilbake i kortets topp, er vi tilbake til ett feilklikk fra å rive
        bort hele bemanningen."""
        from patients.js_test_utils import VAKTLISTE_JS, read_js
        kilde = read_js(VAKTLISTE_JS)
        self.assertNotIn('fjernRessurs', kilde)
        self.assertIn('slettRessurs', kilde)


class KorpsPaaPlassenTests(TilgangsBasis):
    """Reservasjonen finnes på to nivåer, og plassen vinner over ressursen.

    **Andrés bestilling 30. aug. 2026:** en samleplass bemannes av flere
    korps. `Ressurs.korps` reserverer hele ressursen til ett, og da måtte
    samleplassen deles i én ressurs per korps — og da er den ikke lenger én
    samleplass. `Vaktpost.korps` setter av én plass til ett korps.
    """

    def _ledig(self, klient, ressurs, **overstyr):
        kropp = {'fra_tid': self._iso(0), 'til_tid': self._iso(8)}
        kropp.update(overstyr)
        return klient.post(
            f'/vaktliste/api/ressurser/{ressurs.pk}/vaktposter/',
            data=kropp, content_type='application/json')

    def test_plassen_arver_ressursens_reservasjon(self):
        """Tom `korps` betyr «som ressursen», ikke «ingen». Ellers ville
        alle eksisterende plasser blitt fritt vilt ved oppgraderingen."""
        res = self._ledig(self.c_vl, self.res_hgsd)
        self.assertEqual(res.status_code, 201)
        rad = res.json()['data']
        self.assertIsNone(rad['plass_korps_id'], 'ingen egen reservasjon')
        self.assertEqual(rad['reservert_korps_id'], self.hgsd.pk,
                         'men den arver bilens')

    def test_plassens_korps_vinner_over_ressursens(self):
        res = self._ledig(self.c_vl, self.res_hgsd, korps_id=self.karmoy.pk)
        rad = res.json()['data']
        self.assertEqual(rad['plass_korps_id'], self.karmoy.pk)
        self.assertEqual(rad['reservert_korps_id'], self.karmoy.pk)

    def test_korpsbruker_fyller_plassen_satt_av_til_henne(self):
        """Selve poenget: en plass på en ureservert samleplass, satt av til
        Haugesund, skal Haugesunds fører kunne fylle."""
        pk = self._ledig(self.c_vl, self.res_fri,
                         korps_id=self.hgsd.pk).json()['data']['id']
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'mannskap_id': self.p_hgsd.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 200)

    def test_korpsbruker_nektes_plassen_satt_av_til_et_annet_korps(self):
        """To plasser på samme samleplass: én til Haugesund, én til Karmøy.
        Uten dette ville reservasjonen på plassen vært pynt."""
        pk = self._ledig(self.c_vl, self.res_fri,
                         korps_id=self.karmoy.pk).json()['data']['id']
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'mannskap_id': self.p_hgsd.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)

    def test_plassens_korps_stenger_ogsaa_paa_en_reservert_ressurs(self):
        """Bilen er Haugesunds, men denne ene plassen er satt av til Karmøy.
        Da skal Haugesunds fører ikke inn — plassen vinner."""
        pk = self._ledig(self.c_vl, self.res_hgsd,
                         korps_id=self.karmoy.pk).json()['data']['id']
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'mannskap_id': self.p_hgsd.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)

    def test_korpsbruker_kan_ikke_omreservere_en_plass(self):
        """Den korteste veien rundt hele regelen: sett plassens korps til mitt
        eget, og fyll den etterpå."""
        pk = self._ledig(self.c_vl, self.res_fri,
                         korps_id=self.karmoy.pk).json()['data']['id']
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'korps_id': self.hgsd.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Vaktpost.objects.get(pk=pk).korps_id, self.karmoy.pk,
                         'reservasjonen skal stå urørt')

    def test_korpsbruker_kan_ikke_omreservere_sin_egen_plass(self):
        """**Den som avslører hullet.** Testen over stoppes av inngangsporten:
        plassen er en annens, så hun kommer aldri fram til
        reservasjonssjekken. Her er plassen *hennes* — hun får ta i raden — og
        da er det bare den indre sjekken som hindrer henne i å skrive om hvem
        plassen tilhører. Å dele ut er vaktlederens bord, også når det er ens
        egen plass man deler bort.

        Funnet ved mutasjonstesting: uten den indre sjekken var testen over
        fortsatt grønn.
        """
        pk = self._ledig(self.c_vl, self.res_hgsd).json()['data']['id']
        # Hun får fylle den — beviser at porten slipper henne inn.
        self.assertEqual(
            self.c_kb.put(f'/vaktliste/api/vaktposter/{pk}/',
                          data={'merknad': 'min'},
                          content_type='application/json').status_code, 200)
        # Men ikke skrive om hvem den er satt av til.
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'korps_id': self.karmoy.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.assertIsNone(Vaktpost.objects.get(pk=pk).korps_id,
                          'reservasjonen skal stå urørt')

    def test_korpsbruker_kan_ikke_sette_korps_ved_opprettelse(self):
        """Hun oppretter uansett ikke ledige plasser, men regelen skal ikke
        hvile på det ene."""
        res = self._ledig(self.c_kb, self.res_hgsd, korps_id=self.hgsd.pk)
        self.assertEqual(res.status_code, 403)

    def test_lederen_setter_reservasjonen(self):
        pk = self._ledig(self.c_vl, self.res_fri).json()['data']['id']
        res = self.c_vl.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'korps_id': self.karmoy.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Vaktpost.objects.get(pk=pk).korps_id, self.karmoy.pk)

    def test_reservasjonen_kan_fjernes_igjen(self):
        """Tom verdi tilbake til «som ressursen» — ikke en blindvei."""
        pk = self._ledig(self.c_vl, self.res_hgsd,
                         korps_id=self.karmoy.pk).json()['data']['id']
        self.c_vl.put(f'/vaktliste/api/vaktposter/{pk}/',
                      data={'korps_id': None}, content_type='application/json')
        self.assertIsNone(Vaktpost.objects.get(pk=pk).korps_id)
