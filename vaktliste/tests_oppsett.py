"""Tester for vaktlistemodulen — fase 2: oppsettet.

Fasen lovte fire ting, og det er de fire som testes her:

1. En planlagt vakt kan opprettes **uten** at portalens aktive vakt endres.
   Det er fasens farligste bivirkning: hadde `opprett_planlagt_vakt` flyttet
   pekeren, ville pasienter og oppdrag registrert i august havnet på
   oktobervakta uten at noen ba om det.
2. Kopiering tar oppsettet, **aldri** personene.
3. Skiftene har tider som henger sammen, og en dobbeltføring stoppes i basen.
4. Den doble tilgangsregelen (badgen på personen, reservasjonen på ressursen)
   svarer riktig i alle fire hjørnene — selv om ingen endepunkt slipper inn
   på den ennå.

Reglene i punkt 4 håndheves først i fase 3. De testes likevel nå, fordi de er
skrevet nå: en regel uten test er en regel som stemmer helt til noen rører den.
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.models import Vakt
from oppdrag.models import Enhet
from patients.models import AppSetting

from . import choices, services
from .test_helpers import (KO, LAG, MANNSKAPSBIL, SAMLEPLASS, gruppe,
                           lag_ressurs, lag_rolle)
from .models import (Korps, Mannskap, Ressurs, Ressursrolle, Vaktliste,
                     Vaktpost)


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


class PlanlagtVaktTests(TestCase):
    """`opprett_planlagt_vakt` lager vakt og liste — og rører ingenting annet."""

    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        self.aktiv = sett_aktiv_vakt(2098)

    def test_lager_bade_vakt_og_liste(self):
        vl = services.opprett_planlagt_vakt('Landsskytterstevnet 2099')
        self.assertIsInstance(vl, Vaktliste)
        self.assertEqual(vl.vakt.navn, 'Landsskytterstevnet 2099')
        self.assertEqual(vl.status, choices.PLANLEGGING)

    def test_den_nye_vakta_er_ikke_aktiv(self):
        vl = services.opprett_planlagt_vakt('Oktobervakta')
        self.assertFalse(vl.vakt.er_aktiv)

    def test_pekeren_staar_urort(self):
        """Fasens farligste bivirkning, og derfor den viktigste testen her.

        Flyttet planleggingen pekeren, ville pasienter og oppdrag registrert i
        dag havnet på en vakt som ikke har begynt.
        """
        for _ in range(3):
            services.opprett_planlagt_vakt(f'Vakt {_}')
        self.assertEqual(
            AppSetting.objects.get(key='aktiv_vakt_id').value,
            str(self.aktiv.pk))

        from patients.services import hent_aktiv_vakt
        self.assertEqual(hent_aktiv_vakt().pk, self.aktiv.pk)

    def test_aaret_utledes_av_starttiden_ikke_av_i_dag(self):
        """Vakta planlegges i god tid før den går. Året skal følge vakta."""
        start = timezone.make_aware(
            timezone.datetime(2099, 1, 4, 8, 0))
        vl = services.opprett_planlagt_vakt('Nyttårsvakt', startet=start)
        self.assertEqual(vl.vakt.year, 2099)

    def test_tomt_navn_avvises(self):
        for daarlig in ('', '   ', None):
            with self.subTest(navn=daarlig):
                with self.assertRaises(ValueError):
                    services.opprett_planlagt_vakt(daarlig)

    def test_duplikatnavn_avvises_med_forklaring(self):
        services.opprett_planlagt_vakt('Sommervakta')
        with self.assertRaises(ValueError) as ctx:
            services.opprett_planlagt_vakt('Sommervakta')
        self.assertIn('Sommervakta', str(ctx.exception))

    def test_feilet_opprettelse_etterlater_ingen_vakt(self):
        """Transaksjonen: en vakt uten liste ville vært et halvt oppsett."""
        for_ = Vakt.objects.count()
        with self.assertRaises(ValueError):
            services.opprett_planlagt_vakt('  ')
        self.assertEqual(Vakt.objects.count(), for_)

    def test_en_vakt_har_hoyst_en_liste(self):
        vl = services.opprett_planlagt_vakt('Vakt A')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Vaktliste.objects.create(vakt=vl.vakt)


class KopierOppsettTests(TestCase):
    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        self.enhet = Enhet.objects.create(navn='Haugesund 56')
        self.fra = services.opprett_planlagt_vakt('Fjorårets vakt')
        self.til = services.opprett_planlagt_vakt('Årets vakt')

        self.bil = lag_ressurs(
            vaktliste=self.fra, navn='Mannskapsbil 1',
            gruppe=gruppe(MANNSKAPSBIL), korps=self.korps, enhet=self.enhet,
            rekkefolge=10)
        lag_ressurs(
            vaktliste=self.fra, navn='KO', gruppe=gruppe(KO), rekkefolge=20)
        # Rekkefølgen settes normalt av `neste_rekkefolge()`; her settes den
        # eksplisitt fordi testen handler om at kopien bevarer den.

        self.person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        na = timezone.now()
        Vaktpost.objects.create(
            ressurs=self.bil, mannskap=self.person,
            fra_tid=na, til_tid=na + timedelta(hours=8))

    def test_ressursene_kopieres_med_alle_egenskapene(self):
        antall = services.kopier_oppsett(self.fra, self.til)
        self.assertEqual(antall, 2)

        bil = self.til.ressurser.get(navn='Mannskapsbil 1')
        self.assertEqual(bil.gruppe.navn, MANNSKAPSBIL)
        self.assertEqual(bil.korps_id, self.korps.pk)
        self.assertEqual(bil.enhet_id, self.enhet.pk)
        self.assertEqual(bil.rekkefolge, 10)

    def test_personene_kopieres_aldri(self):
        """En liste ingen har sagt ja til er verre enn en tom liste: den ser
        ferdig ut. Regelen står i services-docstringen, og her."""
        services.kopier_oppsett(self.fra, self.til)
        self.assertEqual(
            Vaktpost.objects.filter(ressurs__vaktliste=self.til).count(), 0)
        # … og originalen står urørt.
        self.assertEqual(
            Vaktpost.objects.filter(ressurs__vaktliste=self.fra).count(), 1)

    def test_kopiene_er_egne_rader(self):
        """Ikke delte objekter: endres kopien, står originalen som den var."""
        services.kopier_oppsett(self.fra, self.til)
        kopi = self.til.ressurser.get(navn='KO')
        kopi.navn = 'KO 2'
        kopi.save()
        self.assertTrue(self.fra.ressurser.filter(navn='KO').exists())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class FanerekkefolgeTests(TestCase):
    """`Ressurs.rekkefolge` er det ene stedet rekkefølgen *betyr* noe.

    Fanene på planleggingssiden skal stå i operativ rekkefølge — samleplass,
    biler, lag, KO — og alfabetisk ville stokket om på den («Ambulanse, KO,
    Lag 1, Mannskapsbil 1»). Men brukeren skriver ikke et tall: den som bygger
    vakta legger inn ressursene i den rekkefølgen hun tenker på dem.
    """

    def setUp(self):
        self.vl = services.opprett_planlagt_vakt('Vakta')
        self.c = _klient(_bruker('adm', admin=True))

    def _legg_til(self, navn):
        return self.c.post(
            f'/vaktliste/api/vaktlister/{self.vl.pk}/ressurser/',
            data={'navn': navn, 'gruppe_id': gruppe().pk},
            content_type='application/json')

    def test_fanene_folger_opprettelsesrekkefolgen(self):
        for navn in ('Samleplass', 'Mannskapsbil 1', 'Ambulanse', 'Lag 1', 'KO'):
            self.assertEqual(self._legg_til(navn).status_code, 201)

        data = self.c.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/').json()['data']
        self.assertEqual(
            [r['navn'] for r in data['ressurser']],
            ['Samleplass', 'Mannskapsbil 1', 'Ambulanse', 'Lag 1', 'KO'],
            'alfabetisk ville stokket om på den operative rekkefølgen')

    def test_ingen_maa_skrive_et_tall(self):
        """Kroppen har ingen `rekkefolge`, og radene får likevel ulik verdi."""
        self._legg_til('Først')
        self._legg_til('Så')
        verdier = list(self.vl.ressurser.values_list('rekkefolge', flat=True))
        self.assertEqual(len(set(verdier)), 2, f'ulike verdier, fikk {verdier}')

    def test_steget_gir_plass_til_aa_skyte_inn(self):
        """Steg på 10 slik at en omorganisering senere slipper å nummerere om."""
        self._legg_til('En')
        self._legg_til('To')
        self.assertEqual(
            sorted(self.vl.ressurser.values_list('rekkefolge', flat=True)),
            [10, 20])

    def test_neste_rekkefolge_paa_tom_liste(self):
        self.assertEqual(services.neste_rekkefolge(self.vl), 10)

    def test_lista_er_uavhengig_av_andre_vaktlister(self):
        """Tellingen er per liste — ellers ville fane nummer én på årets vakt
        arvet et tall fra i fjor."""
        annen = services.opprett_planlagt_vakt('Annen vakt')
        self._legg_til('En')
        self.assertEqual(services.neste_rekkefolge(annen), 10)


class ModellReglerTests(TestCase):
    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund')
        self.vl = services.opprett_planlagt_vakt('Vakta')
        self.ressurs = lag_ressurs(
            vaktliste=self.vl, navn='Lag 1', gruppe=gruppe(LAG))
        self.person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        self.na = timezone.now()

    def _post(self, **kwargs):
        kwargs.setdefault('ressurs', self.ressurs)
        kwargs.setdefault('mannskap', self.person)
        kwargs.setdefault('fra_tid', self.na)
        kwargs.setdefault('til_tid', self.na + timedelta(hours=6))
        return Vaktpost.objects.create(**kwargs)

    def test_ressursnavn_er_unikt_per_vaktliste_ikke_globalt(self):
        annen = services.opprett_planlagt_vakt('Annen vakt')
        lag_ressurs(vaktliste=annen, navn='Lag 1')   # går fint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                lag_ressurs(vaktliste=self.vl, navn='Lag 1')

    def test_samme_person_samme_ressurs_samme_starttid_er_dobbeltforing(self):
        self._post()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._post()

    def test_to_skift_paa_samme_ressurs_er_lov(self):
        """Går Per to skift på bilen, er det to rader. Det er nettopp det som
        gjør timer og hviletid (§8b) til spørringer i stedet for tolkning."""
        self._post()
        self._post(fra_tid=self.na + timedelta(hours=12),
                   til_tid=self.na + timedelta(hours=18))
        self.assertEqual(self.ressurs.vaktposter.count(), 2)

    def test_overlapp_paa_tvers_av_ressurser_stoppes_ikke(self):
        """Bevisst: noen ganger står man på to lister. Planleggingstallene
        flagger det (fase 5), basen nekter det ikke."""
        annen = lag_ressurs(vaktliste=self.vl, navn='KO')
        self._post()
        self._post(ressurs=annen)
        self.assertEqual(self.person.vaktposter.count(), 2)

    def test_sletting_av_ressurs_tar_skiftene(self):
        self._post()
        self.ressurs.delete()
        self.assertEqual(Vaktpost.objects.count(), 0)

    def test_mannskap_med_skift_kan_ikke_slettes(self):
        from django.db.models.deletion import ProtectedError
        self._post()
        with self.assertRaises(ProtectedError):
            self.person.delete()

    def test_vakt_med_liste_kan_ikke_slettes(self):
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):
            self.vl.vakt.delete()

    def test_er_tilstede_er_utledet_av_stemplene(self):
        vp = self._post()
        self.assertFalse(vp.er_tilstede, 'ikke møtt ennå')
        vp.mott_at = self.na
        self.assertTrue(vp.er_tilstede)
        vp.av_vakt_at = self.na + timedelta(hours=6)
        self.assertFalse(vp.er_tilstede, 'gått av vakt')

    def test_i_drift_folger_statusen(self):
        self.assertFalse(self.vl.i_drift)
        self.vl.status = choices.DRIFT
        self.assertTrue(self.vl.i_drift)


class TilgangsregelTests(TestCase):
    """Den doble regelen (§4.2), i alle fire hjørnene.

    Håndheves fra fase 3 — men den er skrevet nå, og en regel uten test er en
    regel som stemmer helt til noen rører den.
    """

    def setUp(self):
        self.hgsd = Korps.objects.create(navn='Haugesund')
        self.karmoy = Korps.objects.create(navn='Karmøy')
        self.vl = services.opprett_planlagt_vakt('Vakta')

        self.res_hgsd = lag_ressurs(
            vaktliste=self.vl, navn='Lag HGSD', korps=self.hgsd)
        self.res_karmoy = lag_ressurs(
            vaktliste=self.vl, navn='Lag Karmøy', korps=self.karmoy)
        self.res_fri = lag_ressurs(vaktliste=self.vl, navn='KO')

        self.p_hgsd = Mannskap.objects.create(navn='Kari', korps=self.hgsd)
        self.p_karmoy = Mannskap.objects.create(navn='Ola', korps=self.karmoy)

        # Korps-brukeren: skriv_handling *og* en mannskapsrad i Haugesund.
        self.korpsbruker = _bruker('kb', 'skriv_handling')
        self.p_hgsd.user = self.korpsbruker
        self.p_hgsd.save()

        self.vaktleder = _bruker('vl', 'skriv_full')
        self.leser = _bruker('les', 'les')
        self.admin = _bruker('adm', admin=True)

    def test_badgen_arves_fra_mannskapsraden(self):
        self.assertEqual(services.brukerens_korps(self.korpsbruker), self.hgsd)
        self.assertIsNone(services.brukerens_korps(self.vaktleder))

    def test_korpsbruker_far_sitt_eget_korps(self):
        self.assertTrue(
            services.kan_sette_vaktpost(
                self.korpsbruker, self.res_hgsd, self.p_hgsd))

    def test_korpsbruker_nektes_annet_korps_sin_ressurs(self):
        self.assertFalse(
            services.kan_sette_vaktpost(
                self.korpsbruker, self.res_karmoy, self.p_hgsd))

    def test_korpsbruker_nektes_annet_korps_sin_person(self):
        """Den andre halvdelen. Riktig ressurs er ikke nok — regelen er dobbel,
        og det er derfor den er skrevet som én funksjon."""
        self.assertFalse(
            services.kan_sette_vaktpost(
                self.korpsbruker, self.res_hgsd, self.p_karmoy))

    def test_ureservert_ressurs_er_ikke_et_fristed(self):
        """Tom reservasjon betyr «vaktlederens bord», ikke «fritt fram».
        Motsatt tolkning ville gitt enhver korps-bruker KO og samleplass."""
        self.assertFalse(
            services.kan_bemanne_ressurs(self.korpsbruker, self.res_fri))
        self.assertFalse(
            services.kan_sette_vaktpost(
                self.korpsbruker, self.res_fri, self.p_hgsd))

    def test_skriv_full_blander_fritt(self):
        for ressurs in (self.res_hgsd, self.res_karmoy, self.res_fri):
            for person in (self.p_hgsd, self.p_karmoy):
                with self.subTest(ressurs=ressurs.navn, person=person.navn):
                    self.assertTrue(services.kan_sette_vaktpost(
                        self.vaktleder, ressurs, person))

    def test_admin_blander_fritt_uten_rader(self):
        self.assertTrue(services.kan_sette_vaktpost(
            self.admin, self.res_karmoy, self.p_karmoy))

    def test_les_skriver_ingenting(self):
        self.assertFalse(
            services.kan_sette_vaktpost(self.leser, self.res_fri, self.p_hgsd))
        self.assertFalse(
            services.kan_redigere_mannskap(self.leser, self.p_hgsd))

    def test_konto_uten_mannskapsrad_er_stengt(self):
        """Fail-closed, samme form som en enhetskonto uten enhet: badgen
        mangler, og da finnes det ikke noe korps å avgrense til."""
        uten = _bruker('uten_rad', 'skriv_handling')
        self.assertIsNone(services.brukerens_korps(uten))
        self.assertFalse(services.kan_redigere_mannskap(uten, self.p_hgsd))
        self.assertFalse(services.kan_bemanne_ressurs(uten, self.res_hgsd))

    def test_anonym_bruker_har_ingen_badge(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertIsNone(services.brukerens_korps(AnonymousUser()))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ApiTests(TestCase):
    """Endepunktene. Fase 2 er admin-only — se `vaktliste/module.py`."""

    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        self.aktiv = sett_aktiv_vakt(2098)
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        self.rolle = lag_rolle('Lagleder')
        self.person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        self.admin = _bruker('adm', admin=True)
        self.c = _klient(self.admin)
        self.na = timezone.now()

    def _iso(self, timer=0):
        return (self.na + timedelta(hours=timer)).isoformat()

    def _liste(self, navn='Vakta'):
        return services.opprett_planlagt_vakt(navn)

    def _ressurs(self, vl, navn='Lag 1', **kwargs):
        return lag_ressurs(vaktliste=vl, navn=navn, **kwargs)

    # ── Siden ────────────────────────────────────────────────────────────
    def test_siden_svarer_for_admin(self):
        res = self.c.get('/vaktliste/')
        self.assertEqual(res.status_code, 200)
        # Filnavnet er hashet av ManifestStaticFilesStorage — sjekk stammen.
        self.assertContains(res, 'js/vaktliste')
        self.assertContains(res, 'css/vaktliste')

    def test_siden_nekter_uten_modultilgang(self):
        c = _klient(_bruker('ingen'))
        self.assertEqual(c.get('/vaktliste/').status_code, 403)

    # ── Vaktlister ───────────────────────────────────────────────────────
    def test_post_lager_liste_uten_aa_bytte_aktiv_vakt(self):
        res = self.c.post(
            '/vaktliste/api/vaktlister/',
            data={'navn': 'Oktobervakta'}, content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertFalse(res.json()['data']['er_aktiv_vakt'])

        from patients.services import hent_aktiv_vakt
        self.assertEqual(hent_aktiv_vakt().pk, self.aktiv.pk)

    def test_post_med_kopier_fra_tar_ressursene(self):
        kilde = self._liste('I fjor')
        self._ressurs(kilde, 'Mannskapsbil 1', gruppe=gruppe(MANNSKAPSBIL),
                      korps=self.korps)
        res = self.c.post(
            '/vaktliste/api/vaktlister/',
            data={'navn': 'I år', 'kopier_fra': kilde.pk},
            content_type='application/json')
        self.assertEqual(res.json()['data']['kopierte_ressurser'], 1)

    def test_post_med_duplikatnavn_gir_400_med_forklaring(self):
        self._liste('Sommervakta')
        res = self.c.post(
            '/vaktliste/api/vaktlister/',
            data={'navn': 'Sommervakta'}, content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Sommervakta', res.json()['message'])

    def test_detalj_gir_hele_oppsettet_i_ett_svar(self):
        vl = self._liste()
        r = self._ressurs(vl)
        Vaktpost.objects.create(
            ressurs=r, mannskap=self.person, rolle=self.rolle,
            fra_tid=self.na, til_tid=self.na + timedelta(hours=8))

        data = self.c.get(f'/vaktliste/api/vaktlister/{vl.pk}/').json()['data']
        self.assertEqual(len(data['ressurser']), 1)
        self.assertEqual(len(data['vaktposter']), 1)
        self.assertEqual(data['vaktposter'][0]['rolle'], 'Lagleder')
        self.assertEqual(data['vaktposter'][0]['korps_kort'], 'HGSD')
        for nokkel in ('korps', 'roller', 'mannskap', 'enheter'):
            self.assertIn(nokkel, data)

    def test_inaktivt_mannskap_tilbys_ikke(self):
        vl = self._liste()
        Mannskap.objects.create(navn='Pensjonert', korps=self.korps,
                                er_aktiv=False)
        data = self.c.get(f'/vaktliste/api/vaktlister/{vl.pk}/').json()['data']
        self.assertEqual([m['navn'] for m in data['mannskap']], ['Kari'])

    def test_slett_liste_krever_bekreftelse_og_lar_vakta_staa(self):
        vl = self._liste()
        vakt_pk = vl.vakt_id
        sti = f'/vaktliste/api/vaktlister/{vl.pk}/'

        self.assertEqual(self.c.delete(sti).status_code, 400)
        self.assertTrue(Vaktliste.objects.filter(pk=vl.pk).exists())

        res = self.c.delete(sti, data={'confirm': True},
                            content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Vaktliste.objects.filter(pk=vl.pk).exists())
        self.assertTrue(Vakt.objects.filter(pk=vakt_pk).exists())

    def test_ukjent_liste_gir_404(self):
        self.assertEqual(
            self.c.get('/vaktliste/api/vaktlister/9999/').status_code, 404)

    # ── Ressurser ────────────────────────────────────────────────────────
    def test_gruppa_kan_finnes_i_ett_eksemplar(self):
        """Samleplassen og KO er samlingspunkt for flere korps, ikke flåter.
        Migrasjon 0009 setter flagget for de to."""
        from .models import Ressursgruppe
        self.assertFalse(Ressursgruppe.objects.get(navn='Samleplass').flere_enheter)
        self.assertFalse(Ressursgruppe.objects.get(navn='KO').flere_enheter)
        for navn in ('Ambulanse', 'Mannskapsbil', 'Lag', 'Annet'):
            with self.subTest(gruppe=navn):
                self.assertTrue(
                    Ressursgruppe.objects.get(navn=navn).flere_enheter,
                    'flåter beholder muligheten til å legge til flere')

    def test_ny_gruppe_er_en_flaate_som_standard(self):
        res = self.c.post('/vaktliste/api/grupper/',
                          data={'navn': 'MC-patrulje'},
                          content_type='application/json')
        self.assertTrue(res.json()['data']['flere_enheter'])

    def test_ny_gruppe_kan_settes_til_ett_eksemplar(self):
        res = self.c.post('/vaktliste/api/grupper/',
                          data={'navn': 'Innsatsleder', 'flere_enheter': False},
                          content_type='application/json')
        self.assertFalse(res.json()['data']['flere_enheter'])

    def test_enkeltgruppa_tar_imot_den_forste(self):
        """Uten dette var en enkeltgruppe en blindvei."""
        vl = self._liste()
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'Samleplass', 'gruppe_id': gruppe(SAMLEPLASS).pk},
            content_type='application/json')
        self.assertEqual(201, res.status_code, res.content)

    def test_enkeltgruppa_nekter_nummer_to(self):
        """Regelen står i grensesnittet — knappen er borte, gruppa er ute av
        nedtrekket — men et bart POST når hit, og en regel som bare finnes i
        klienten er ingen regel."""
        vl = self._liste()
        lag_ressurs(vaktliste=vl, navn='Samleplass',
                    gruppe=gruppe(SAMLEPLASS))
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'Samleplass 2', 'gruppe_id': gruppe(SAMLEPLASS).pk},
            content_type='application/json')
        self.assertEqual(400, res.status_code)
        self.assertIn('ett eksemplar', res.json()['message'])
        self.assertEqual(1, Ressurs.objects.filter(vaktliste=vl).count())

    def test_flaaten_tar_imot_bil_b(self):
        """Speilet av forrige: «Ambulanse» rommer bil A, bil B og bil C."""
        vl = self._liste()
        lag_ressurs(vaktliste=vl, navn='Bil A',
                    gruppe=gruppe(MANNSKAPSBIL))
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'Bil B', 'gruppe_id': gruppe(MANNSKAPSBIL).pk},
            content_type='application/json')
        self.assertEqual(201, res.status_code, res.content)

    def test_enkeltgruppa_sperrer_bare_sin_egen_vaktliste(self):
        """Sperren er per vaktliste. Er den global, kan neste vakt ikke ha
        samleplass i det hele tatt."""
        forrige = self._liste()
        lag_ressurs(vaktliste=forrige, navn='Samleplass',
                    gruppe=gruppe(SAMLEPLASS))
        ny = self._liste(navn='Neste vakt')
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{ny.pk}/ressurser/',
            data={'navn': 'Samleplass', 'gruppe_id': gruppe(SAMLEPLASS).pk},
            content_type='application/json')
        self.assertEqual(201, res.status_code, res.content)

    def test_ressurs_opprettes_med_reservasjon(self):
        vl = self._liste()
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'Lag Nord', 'gruppe_id': gruppe(LAG).pk,
                  'korps_id': self.korps.pk},
            content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['data']['korps_navn'], 'Haugesund')

    def test_ressurs_uten_korps_er_ureservert(self):
        vl = self._liste()
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'KO', 'gruppe_id': gruppe(KO).pk},
            content_type='application/json')
        self.assertIsNone(res.json()['data']['korps_id'])

    def test_ressurs_uten_gruppe_avvises(self):
        """Gruppa styrer ikon, fane, roller og kurve. En ressurs uten gruppe
        er en fane uten navn og et nedtrekk uten innhold — den skal ikke
        kunne opprettes, ikke opprettes med en stille standardverdi."""
        vl = self._liste()
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'Noe'}, content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('gruppe', res.json()['message'])

    def test_ukjent_gruppe_avvises(self):
        vl = self._liste()
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'Noe', 'gruppe_id': 99999},
            content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_duplikat_ressursnavn_gir_lesbar_400(self):
        """Skranken i basen er fasit for duplikater — en `exists()` foran
        skrivingen er et kappløp. Men `IntegrityError` må fanges rundt et
        savepoint, ellers er transaksjonen ubrukelig etterpå og sesjonslagringen
        river feilmeldingen bort og etterlater en naken 400-side.
        """
        vl = self._liste()
        self._ressurs(vl, 'Lag 1')
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'Lag 1', 'gruppe_id': gruppe().pk},
            content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Lag 1', res.json()['message'])

    def test_duplikat_navn_ved_endring_gir_lesbar_400(self):
        vl = self._liste()
        self._ressurs(vl, 'Lag 1')
        r2 = self._ressurs(vl, 'Lag 2')
        res = self.c.put(
            f'/vaktliste/api/ressurser/{r2.pk}/',
            data={'navn': 'Lag 1'}, content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Lag 1', res.json()['message'])

    def test_tomt_ressursnavn_avvises(self):
        vl = self._liste()
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': '   ', 'gruppe_id': gruppe().pk},
            content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_ressurs_kan_endres_og_fjernes(self):
        vl = self._liste()
        r = self._ressurs(vl)
        res = self.c.put(
            f'/vaktliste/api/ressurser/{r.pk}/',
            data={'navn': 'Lag Sør', 'korps_id': self.korps.pk},
            content_type='application/json')
        self.assertEqual(res.json()['data']['navn'], 'Lag Sør')

        # Sletting krever bekreftelse: CASCADE tar alle skiftene med seg.
        self.assertEqual(
            self.c.delete(f'/vaktliste/api/ressurser/{r.pk}/').status_code, 400)
        self.assertTrue(Ressurs.objects.filter(pk=r.pk).exists())

        self.assertEqual(
            self.c.delete(f'/vaktliste/api/ressurser/{r.pk}/',
                          data={'confirm': True},
                          content_type='application/json').status_code, 200)
        self.assertFalse(Ressurs.objects.filter(pk=r.pk).exists())

    # ── Vaktposter ───────────────────────────────────────────────────────
    def _sett_paa(self, ressurs, **overstyr):
        kropp = {'mannskap_id': self.person.pk, 'rolle_id': self.rolle.pk,
                 'fra_tid': self._iso(0), 'til_tid': self._iso(8)}
        kropp.update(overstyr)
        return self.c.post(
            f'/vaktliste/api/ressurser/{ressurs.pk}/vaktposter/',
            data=kropp, content_type='application/json')

    def test_person_settes_paa_vakt(self):
        r = self._ressurs(self._liste())
        res = self._sett_paa(r)
        self.assertEqual(res.status_code, 201)
        data = res.json()['data']
        self.assertEqual(data['navn'], 'Kari')
        self.assertFalse(data['tilstede'], 'ingen er møtt før drift (fase 4)')
        self.assertIsNone(data['mott_at'])

    def test_skift_som_slutter_for_det_begynner_avvises(self):
        """Ville gitt negativ skiftlengde i planleggingstallene (§8b).
        Stopp der brukeren kan rette det, ikke i en aggregering senere."""
        r = self._ressurs(self._liste())
        for til in (self._iso(-1), self._iso(0)):
            with self.subTest(til=til):
                res = self._sett_paa(r, til_tid=til)
                self.assertEqual(res.status_code, 400)
        self.assertEqual(Vaktpost.objects.count(), 0)

    def test_skift_uten_tider_avvises(self):
        r = self._ressurs(self._liste())
        for mangel in ({'fra_tid': None}, {'til_tid': None},
                       {'fra_tid': 'i morgen tidlig'}):
            with self.subTest(mangel=mangel):
                self.assertEqual(self._sett_paa(r, **mangel).status_code, 400)

    def test_ukjent_mannskap_avvises(self):
        """En ID som ikke finnes er en feil. **Tom er noe annet:** det er en
        ledig plass — se `LedigePlasserTests`."""
        r = self._ressurs(self._liste())
        for daarlig in (9999, 'kari'):
            with self.subTest(id=daarlig):
                self.assertEqual(
                    self._sett_paa(r, mannskap_id=daarlig).status_code, 400)

    def test_dobbeltforing_gir_400_ikke_500(self):
        r = self._ressurs(self._liste())
        self._sett_paa(r)
        res = self._sett_paa(r)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Kari', res.json()['message'])

    def test_vaktpost_kan_endres(self):
        r = self._ressurs(self._liste())
        pk = self._sett_paa(r).json()['data']['id']
        res = self.c.put(
            f'/vaktliste/api/vaktposter/{pk}/',
            data={'til_tid': self._iso(12), 'merknad': 'Kommer sent'},
            content_type='application/json')
        self.assertEqual(res.json()['data']['merknad'], 'Kommer sent')

    def test_endring_til_ugyldig_tidsspenn_avvises(self):
        r = self._ressurs(self._liste())
        pk = self._sett_paa(r).json()['data']['id']
        res = self.c.put(
            f'/vaktliste/api/vaktposter/{pk}/',
            data={'til_tid': self._iso(-2)}, content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            Vaktpost.objects.get(pk=pk).til_tid.isoformat(), self._iso(8))

    def test_vaktpost_kan_fjernes(self):
        r = self._ressurs(self._liste())
        pk = self._sett_paa(r).json()['data']['id']
        self.assertEqual(
            self.c.delete(f'/vaktliste/api/vaktposter/{pk}/').status_code, 200)
        self.assertEqual(Vaktpost.objects.count(), 0)

    # Tilgangsmatrisen for fase 3 står i `tests_tilgang.py`. Den hører ikke
    # hjemme her: dette er endepunktenes oppførsel, den er hvem som slipper
    # inn på dem — og de to endres av ulike grunner.


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RessurstabellensDataTests(TestCase):
    """Ressurstabellen skal kunne vurderes uten å bla til registeret.

    Bestillingen bak kompetansekolonnen var å se **helhetlig sammensetning**
    av et lag: har vi en sjåfør, har vi noen med AFØR. Det krever at
    kompetansene følger med vaktposten, ikke bare mannskapsraden.

    `rolle_id` følger `rolle` fordi rollen redigeres i raden nå — en
    nedtrekksliste trenger IDen for å vite hva som er valgt.
    """

    def setUp(self):
        from vaktliste.models import Kompetanse
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        self.gfor = Kompetanse.objects.create(navn='GFØR')
        self.afor = Kompetanse.objects.create(navn='AFØR', bygger_paa=self.gfor)
        self.syk = Kompetanse.objects.create(navn='Sykepleier')
        self.rolle = lag_rolle('Lagleder')

        self.vl = services.opprett_planlagt_vakt('Vakta')
        self.ressurs = lag_ressurs(vaktliste=self.vl, navn='Lag 1')
        self.person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        self.person.kompetanser.set([self.gfor, self.afor, self.syk])
        na = timezone.now()
        self.vp = Vaktpost.objects.create(
            ressurs=self.ressurs, mannskap=self.person, rolle=self.rolle,
            fra_tid=na, til_tid=na + timedelta(hours=8))
        self.c = _klient(_bruker('adm', admin=True))

    def _vaktpost(self):
        data = self.c.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/').json()['data']
        return data['vaktposter'][0]

    def test_kompetansene_folger_vaktposten(self):
        self.assertEqual(sorted(self._vaktpost()['kompetanser']),
                         ['AFØR', 'Sykepleier'])

    def test_stigen_gjelder_ogsaa_her(self):
        """GFØR er implisert av AFØR, og skal ikke fylle kolonnen."""
        self.assertNotIn('GFØR', self._vaktpost()['kompetanser'])

    def test_rolle_id_folger_med_til_nedtrekket(self):
        self.assertEqual(self._vaktpost()['rolle_id'], self.rolle.pk)
        self.assertEqual(self._vaktpost()['rolle'], 'Lagleder')

    def test_person_uten_kompetanse_gir_tom_liste(self):
        annen = Mannskap.objects.create(navn='Ola', korps=self.korps)
        na = timezone.now()
        Vaktpost.objects.create(
            ressurs=self.ressurs, mannskap=annen,
            fra_tid=na + timedelta(hours=12), til_tid=na + timedelta(hours=20))
        data = self.c.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/').json()['data']
        tom = [v for v in data['vaktposter'] if v['navn'] == 'Ola'][0]
        self.assertEqual(tom['kompetanser'], [])

    def test_skrivestiene_gir_samme_form_som_lesestien(self):
        """Raden tegnes på nytt fra PUT-svaret. Manglet kompetansene der,
        ville kolonnen tømt seg selv i det man endret rollen."""
        res = self.c.put(f'/vaktliste/api/vaktposter/{self.vp.pk}/',
                         data={'merknad': 'Kommer sent'},
                         content_type='application/json')
        etter = res.json()['data']
        self.assertEqual(sorted(etter['kompetanser']), ['AFØR', 'Sykepleier'])
        self.assertIn('rolle_id', etter)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LedigePlasserTests(TestCase):
    """En ledig plass er et skift som mangler en person.

    Planlegging begynner med behovet — «Lag 1 trenger fire, én av dem
    lagleder» — og personene fylles inn etter hvert. Derfor er
    `Vaktpost.mannskap` nullbar framfor at det finnes en egen
    plassholder-modell: tider, rolle og ressurs virker allerede, og «å fylle
    plassen» er én feltendring i stedet for en flytting mellom to tabeller.
    """

    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        self.rolle = lag_rolle('Lagleder')
        self.vl = services.opprett_planlagt_vakt('Vakta')
        self.ressurs = lag_ressurs(vaktliste=self.vl, navn='Lag 1')
        self.person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        self.c = _klient(_bruker('adm', admin=True))
        self.na = timezone.now()

    def _iso(self, timer=0):
        return (self.na + timedelta(hours=timer)).isoformat()

    def _plass(self, **overstyr):
        kropp = {'fra_tid': self._iso(0), 'til_tid': self._iso(8)}
        kropp.update(overstyr)
        return self.c.post(
            f'/vaktliste/api/ressurser/{self.ressurs.pk}/vaktposter/',
            data=kropp, content_type='application/json')

    def test_plass_uten_person_opprettes(self):
        res = self._plass(rolle_id=self.rolle.pk)
        self.assertEqual(res.status_code, 201)
        data = res.json()['data']
        self.assertTrue(data['ledig'])
        self.assertIsNone(data['mannskap_id'])
        self.assertEqual(data['rolle'], 'Lagleder')

    def test_flere_like_plasser_i_ett_kall(self):
        """Fire tomme plasser på et lag skal ikke være fire klikk."""
        res = self._plass(antall=4)
        self.assertEqual(res.json()['data']['antall_opprettet'], 4)
        self.assertEqual(Vaktpost.objects.count(), 4)

    def test_identiske_ledige_plasser_bryter_ikke_skranken(self):
        """NULL er ikke lik NULL i en unik-skranke — og det er nettopp det
        som gjør at man kan sette opp fire tomme plasser til samme tid."""
        self._plass()
        self.assertEqual(self._plass().status_code, 201)
        self.assertEqual(Vaktpost.objects.count(), 2)

    def test_antall_gjelder_ikke_naar_en_person_er_valgt(self):
        """To identiske rader med samme person ville brutt skranken."""
        res = self._plass(mannskap_id=self.person.pk, antall=4)
        self.assertEqual(res.json()['data']['antall_opprettet'], 1)

    def test_urimelig_antall_avvises(self):
        for daarlig in (0, -3, 999):
            with self.subTest(antall=daarlig):
                self.assertEqual(self._plass(antall=daarlig).status_code, 400)
        self.assertEqual(Vaktpost.objects.count(), 0)

    def test_plassen_fylles_med_en_feltendring(self):
        pk = self._plass().json()['data']['id']
        res = self.c.put(f'/vaktliste/api/vaktposter/{pk}/',
                         data={'mannskap_id': self.person.pk},
                         content_type='application/json')
        data = res.json()['data']
        self.assertFalse(data['ledig'])
        self.assertEqual(data['navn'], 'Kari')

    def test_plassen_kan_tommes_igjen(self):
        """Noen melder avbud i planleggingsfasen — da er plassen ledig på
        nytt, ikke slettet."""
        pk = self._plass(mannskap_id=self.person.pk).json()['data']['id']
        res = self.c.put(f'/vaktliste/api/vaktposter/{pk}/',
                         data={'mannskap_id': None},
                         content_type='application/json')
        self.assertTrue(res.json()['data']['ledig'])

    def test_ukjent_person_avvises_ved_fylling(self):
        pk = self._plass().json()['data']['id']
        res = self.c.put(f'/vaktliste/api/vaktposter/{pk}/',
                         data={'mannskap_id': 9999},
                         content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_ledig_plass_er_ikke_tilstede(self):
        pk = self._plass().json()['data']['id']
        vp = Vaktpost.objects.get(pk=pk)
        vp.mott_at = self.na
        self.assertFalse(vp.er_tilstede, 'ingen kan møte på en tom plass')

    def test_str_sier_ledig_plass(self):
        pk = self._plass().json()['data']['id']
        self.assertIn('Ledig plass', str(Vaktpost.objects.get(pk=pk)))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VaktlengdeTests(TestCase):
    """Vakta må kunne få og endre en lengde etter at den er opprettet.

    Spennet er det bemanningskurven tegnes over. Uten det kunne kurven bare
    vise fra første til siste skift — og da er hullet i begynnelsen usynlig
    nettopp fordi ingen er satt opp der ennå.
    """

    def setUp(self):
        self.start = timezone.now()
        self.vl = services.opprett_planlagt_vakt('Vakta', startet=self.start)
        self.c = _klient(_bruker('adm', admin=True))

    def _put(self, **kropp):
        return self.c.put(f'/vaktliste/api/vaktlister/{self.vl.pk}/',
                          data=kropp, content_type='application/json')

    def test_slutt_kan_settes(self):
        slutt = self.start + timedelta(hours=36)
        res = self._put(planlagt_slutt=slutt.isoformat())
        self.assertEqual(res.status_code, 200)
        self.vl.refresh_from_db()
        self.assertIsNotNone(self.vl.planlagt_slutt)

    def test_start_kan_flyttes(self):
        ny = self.start + timedelta(days=7)
        self._put(startet=ny.isoformat())
        self.vl.vakt.refresh_from_db()
        self.assertEqual(self.vl.vakt.startet.date(), ny.date())

    def test_aaret_folger_starten(self):
        """Vakta kan flyttes over et årsskifte mens den planlegges, og `year`
        er portalens scope-nøkkel."""
        ny = timezone.make_aware(timezone.datetime(2099, 3, 1, 8, 0))
        self._put(startet=ny.isoformat())
        self.vl.vakt.refresh_from_db()
        self.assertEqual(self.vl.vakt.year, 2099)

    def test_slutt_for_start_avvises(self):
        res = self._put(planlagt_slutt=(self.start - timedelta(hours=1)).isoformat())
        self.assertEqual(res.status_code, 400)
        self.vl.refresh_from_db()
        self.assertIsNone(self.vl.planlagt_slutt)

    def test_tom_start_avvises(self):
        res = self._put(startet=None)
        self.assertEqual(res.status_code, 400)

    def test_slutt_kan_fjernes(self):
        self._put(planlagt_slutt=(self.start + timedelta(hours=8)).isoformat())
        self._put(planlagt_slutt=None)
        self.vl.refresh_from_db()
        self.assertIsNone(self.vl.planlagt_slutt)

    def test_spennet_ligger_i_svaret(self):
        slutt = self.start + timedelta(hours=8)
        self._put(planlagt_slutt=slutt.isoformat())
        data = self.c.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/').json()['data']
        self.assertIsNotNone(data['vaktliste']['planlagt_slutt'])

    def test_services_vaktspenn_krever_begge_ender(self):
        self.assertEqual(services.vaktspenn(self.vl), (None, None))
        self.vl.planlagt_slutt = self.start + timedelta(hours=8)
        self.vl.save()
        start, slutt = services.vaktspenn(self.vl)
        self.assertIsNotNone(start)
        self.assertIsNotNone(slutt)

    def test_lengden_er_skriv_full(self):
        """Spennet gjelder hele vakta, ikke ett korps' del av den."""
        for nivaa in ('les', 'skriv_handling'):
            with self.subTest(nivaa=nivaa):
                c = _klient(_bruker(f'b_{nivaa}', nivaa))
                res = c.put(f'/vaktliste/api/vaktlister/{self.vl.pk}/',
                            data={'planlagt_slutt': None},
                            content_type='application/json')
                self.assertEqual(res.status_code, 403)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RessursrolleTests(TestCase):
    """Rollen gjelder **ressursen**, ikke vakta — derfor navnet.

    Het `VaktRolle` til 30. aug. 2026. Samme person er sjåfør på
    mannskapsbilen lørdag og lagleder på samleplassen søndag, og det er
    nettopp derfor rollen sitter på `Vaktpost` og ikke på `Mannskap`.

    Administreres fra planleggingssiden, der den brukes. Rollene må derfor
    komme med i **samme form** i planleggingssvaret som fra `/api/roller/` —
    manageren trenger `i_bruk`, og to former skrevet hver for seg glir fra
    hverandre.
    """

    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund')
        self.rolle = lag_rolle('Lagleder')
        self.utgatt = lag_rolle('Utgått', er_aktiv=False)
        self.vl = services.opprett_planlagt_vakt('Vakta')
        self.ressurs = lag_ressurs(vaktliste=self.vl, navn='Lag 1')
        self.person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        na = timezone.now()
        Vaktpost.objects.create(ressurs=self.ressurs, mannskap=self.person,
                                rolle=self.rolle, fra_tid=na,
                                til_tid=na + timedelta(hours=8))
        self.c = _klient(_bruker('adm', admin=True))

    def _roller(self):
        data = self.c.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/').json()['data']
        return data['roller']

    def test_planleggingssvaret_har_samme_form_som_registeret(self):
        fra_registeret = self.c.get('/vaktliste/api/roller/').json()['data']
        self.assertEqual(self._roller(), fra_registeret)

    def test_i_bruk_naar_fram_til_manageren(self):
        rad = [r for r in self._roller() if r['navn'] == 'Lagleder'][0]
        self.assertEqual(rad['i_bruk'], 1)

    def test_inaktive_roller_sendes_ogsaa(self):
        """Manageren skal vise dem — nedtrekket filtrerer dem bort selv."""
        self.assertIn('Utgått', [r['navn'] for r in self._roller()])

    def test_rolle_i_bruk_kan_ikke_slettes(self):
        res = self.c.delete(f'/vaktliste/api/roller/{self.rolle.pk}/')
        self.assertEqual(res.status_code, 409)

    def test_ubrukt_rolle_kan_slettes_fra_planleggingssiden(self):
        self.assertEqual(
            self.c.delete(f'/vaktliste/api/roller/{self.utgatt.pk}/').status_code,
            200)

    def test_rollen_heter_ressursrolle(self):
        self.assertEqual(Ressursrolle._meta.verbose_name, 'Ressursrolle')
        self.assertEqual(Ressursrolle._meta.verbose_name_plural, 'Ressursroller')
