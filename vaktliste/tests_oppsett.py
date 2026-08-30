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
from .models import Korps, Mannskap, Ressurs, VaktRolle, Vaktliste, Vaktpost


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

        self.bil = Ressurs.objects.create(
            vaktliste=self.fra, navn='Mannskapsbil 1',
            type=choices.MANNSKAPSBIL, korps=self.korps, enhet=self.enhet,
            rekkefolge=10)
        Ressurs.objects.create(
            vaktliste=self.fra, navn='KO', type=choices.KO, rekkefolge=20)
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
        self.assertEqual(bil.type, choices.MANNSKAPSBIL)
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
            data={'navn': navn}, content_type='application/json')

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
        self.ressurs = Ressurs.objects.create(
            vaktliste=self.vl, navn='Lag 1', type=choices.LAG)
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
        Ressurs.objects.create(vaktliste=annen, navn='Lag 1')   # går fint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Ressurs.objects.create(vaktliste=self.vl, navn='Lag 1')

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
        annen = Ressurs.objects.create(vaktliste=self.vl, navn='KO')
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

        self.res_hgsd = Ressurs.objects.create(
            vaktliste=self.vl, navn='Lag HGSD', korps=self.hgsd)
        self.res_karmoy = Ressurs.objects.create(
            vaktliste=self.vl, navn='Lag Karmøy', korps=self.karmoy)
        self.res_fri = Ressurs.objects.create(vaktliste=self.vl, navn='KO')

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
        self.rolle = VaktRolle.objects.create(navn='Lagleder')
        self.person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        self.admin = _bruker('adm', admin=True)
        self.c = _klient(self.admin)
        self.na = timezone.now()

    def _iso(self, timer=0):
        return (self.na + timedelta(hours=timer)).isoformat()

    def _liste(self, navn='Vakta'):
        return services.opprett_planlagt_vakt(navn)

    def _ressurs(self, vl, navn='Lag 1', **kwargs):
        return Ressurs.objects.create(vaktliste=vl, navn=navn, **kwargs)

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
        self._ressurs(kilde, 'Mannskapsbil 1', type=choices.MANNSKAPSBIL,
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
    def test_ressurs_opprettes_med_reservasjon(self):
        vl = self._liste()
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'Lag Nord', 'type': choices.LAG,
                  'korps_id': self.korps.pk},
            content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['data']['korps_navn'], 'Haugesund')

    def test_ressurs_uten_korps_er_ureservert(self):
        vl = self._liste()
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'KO', 'type': choices.KO},
            content_type='application/json')
        self.assertIsNone(res.json()['data']['korps_id'])

    def test_ukjent_ressurstype_avvises(self):
        vl = self._liste()
        res = self.c.post(
            f'/vaktliste/api/vaktlister/{vl.pk}/ressurser/',
            data={'navn': 'Noe', 'type': 'helikopter'},
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
            data={'navn': 'Lag 1'}, content_type='application/json')
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
            data={'navn': '   '}, content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_ressurs_kan_endres_og_fjernes(self):
        vl = self._liste()
        r = self._ressurs(vl)
        res = self.c.put(
            f'/vaktliste/api/ressurser/{r.pk}/',
            data={'navn': 'Lag Sør', 'korps_id': self.korps.pk},
            content_type='application/json')
        self.assertEqual(res.json()['data']['navn'], 'Lag Sør')

        self.assertEqual(
            self.c.delete(f'/vaktliste/api/ressurser/{r.pk}/').status_code, 200)
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
        r = self._ressurs(self._liste())
        for daarlig in (9999, None, 'kari'):
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
