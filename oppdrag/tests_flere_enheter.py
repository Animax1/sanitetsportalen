"""Flere enheter på ett oppdrag — trinn 1 (11. sep. 2026).

`docs/BESLUTNING_FLERE_ENHETER_PER_OPPDRAG.md`. Det som testes er reglene
modellen hviler på, ikke flatene (de kommer i trinn 2–3):

* Én statusmelding er *én enhets* utsagn — kjeden går per koblingsrad.
* Oppdragets status er **utledet**: den mest aktive vinner, `Ledig` bare
  når alle er ledige, og det er da tavla ryddes.
* Bilen ser hvem som er varslet, ikke hva de gjør (§7.3).
* Broen: all kode som fortsatt oppretter oppdrag med `enhet` får én
  koblingsrad uten å vite om den.
"""
from datetime import timedelta

from django.apps import apps
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.backup import KIND_MANUAL, create_backup, restore_backup

from oppdrag import choices, services
from oppdrag.models import Enhet, Lokasjon, Oppdrag, Oppdragsenhet, Statusmelding


AAR = 2098


def _bruker(navn, nivaa=None, *, admin=False):
    b = CustomUser.objects.create_user(
        username=navn, password='x', role='admin' if admin else 'bruker',
        must_change_password=False)
    if nivaa:
        ModulTilgang.objects.create(bruker=b, modul_slug='oppdrag', nivaa=nivaa)
    return b


def _klient(bruker):
    c = Client()
    c.force_login(bruker)
    return c


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class FlereEnheterBasis(TestCase):
    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        self.vakt = sett_aktiv_vakt(AAR)
        self.lokasjon = Lokasjon.objects.create(navn='Hovedscene')
        self.a = Enhet.objects.create(navn='Haugesund 56')
        self.b = Enhet.objects.create(navn='Karmøy 12')
        self.c = Enhet.objects.create(navn='Tysvær 3')

    def _oppdrag(self, enhet=None, **kwargs):
        kwargs.setdefault('oppdragsnummer', services.neste_oppdragsnummer(self.vakt))
        return Oppdrag.objects.create(
            vakt=self.vakt, enhet=enhet or self.a,
            problemstilling='Pustevansker', hastegrad='Akutt',
            lokasjon=self.lokasjon, **kwargs)

    def _to_enheter(self):
        o = self._oppdrag(self.a)
        services.varsle_enhet(o, self.b)
        return o


class BroenTests(FlereEnheterBasis):
    """`Oppdrag.enhet` lever til deploy 2, og all eldre kode går gjennom den."""

    def test_oppdrag_med_enhet_faar_en_koblingsrad(self):
        o = self._oppdrag(self.a, status=choices.FREMME)
        rader = list(o.enheter.all())
        self.assertEqual(len(rader), 1)
        self.assertEqual(rader[0].enhet, self.a)
        self.assertEqual(rader[0].status, choices.FREMME)
        self.assertEqual(o.primaer, rader[0])

    def test_melding_uten_koblingsrad_havner_paa_den_primaere(self):
        o = self._to_enheter()
        m = Statusmelding.objects.create(
            oppdrag=o, status=choices.RYKKER_UT, tidspunkt=timezone.now())
        self.assertEqual(m.oppdragsenhet, o.primaer)
        self.assertEqual(m.oppdragsenhet.enhet, self.a)

    def test_melding_med_bare_koblingsrad_faar_oppdraget(self):
        o = self._to_enheter()
        rad = services.koblingsrad(o, self.b)
        m = Statusmelding.objects.create(
            oppdragsenhet=rad, status=choices.RYKKER_UT, tidspunkt=timezone.now())
        self.assertEqual(m.oppdrag, o)

    def test_backfillen_gir_hvert_oppdrag_en_rad_og_meldingene_peker_paa_den(self):
        """`0011.fyll` kjørt mot rader i den historiske formen."""
        from importlib import import_module
        fyll = import_module('oppdrag.migrations.0011_fyll_oppdragsenhet').fyll
        o = self._oppdrag(self.a, status=choices.FREMME)
        for st in (choices.RYKKER_UT, choices.FREMME):
            Statusmelding.objects.create(oppdrag=o, status=st, tidspunkt=timezone.now())
        # Tilbake til før 0010: ingen koblingsrad, meldingene peker på ingenting.
        Statusmelding.objects.filter(oppdrag=o).update(oppdragsenhet=None)
        o.enheter.all().delete()

        fyll(apps, None)

        rad = o.enheter.get()
        self.assertEqual((rad.enhet, rad.status, rad.rekkefolge), (self.a, choices.FREMME, 0))
        self.assertEqual(
            set(Statusmelding.objects.filter(oppdrag=o).values_list('oppdragsenhet_id', flat=True)),
            {rad.pk})
        # Idempotent: et oppdrag som alt har rad får ikke en til.
        fyll(apps, None)
        self.assertEqual(o.enheter.count(), 1)


class UtledetStatusTests(FlereEnheterBasis):
    """§2.2: den mest aktive vinner, `Ledig` bare når alle er ledige."""

    def test_en_enhet_gir_samme_svar_som_foer(self):
        o = self._oppdrag(self.a)
        services.sett_status(o, choices.RYKKER_UT)
        o.refresh_from_db()
        self.assertEqual(o.status, choices.RYKKER_UT)

    def test_den_mest_aktive_vinner(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(o, choices.FREMME, enhet=self.a)
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        o.refresh_from_db()
        self.assertEqual(o.status, choices.FREMME)
        # B har ikke kommet fram, og det står på hennes rad.
        self.assertEqual(services.koblingsrad(o, self.b).status, choices.RYKKER_UT)

    def test_ledig_bare_naar_alle_er_ledige(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        services.sett_status(o, choices.LEDIG, enhet=self.a)
        o.refresh_from_db()
        self.assertEqual(o.status, choices.RYKKER_UT)
        self.assertIsNone(o.historikk_fra, 'B kjører fortsatt — tavla skal ikke ryddes')
        services.sett_status(o, choices.LEDIG, enhet=self.b)
        o.refresh_from_db()
        self.assertEqual(o.status, choices.LEDIG)
        self.assertIsNotNone(o.historikk_fra)

    def test_en_ventende_enhet_holder_oppdraget_aapent(self):
        """Ledig fra den ene mens den andre ennå ikke har rykket ut: `Venter`."""
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(o, choices.LEDIG, enhet=self.a)
        o.refresh_from_db()
        self.assertEqual(o.status, choices.VENTER)
        self.assertIsNone(o.historikk_fra)


class KjedePerEnhetTests(FlereEnheterBasis):
    """En melding er én enhets utsagn, og overgangene måles per rad."""

    def test_overgangen_maales_mot_enhetens_egen_rad(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        # A står i Rykker ut; B står i Venter og kan ikke gå til Fremme.
        with self.assertRaises(services.UlovligOvergang):
            services.sett_status(o, choices.FREMME, enhet=self.b)

    def test_meldingen_peker_paa_riktig_rad(self):
        o = self._to_enheter()
        m = services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        self.assertEqual(m.oppdragsenhet.enhet, self.b)
        self.assertEqual(services.koblingsrad(o, self.a).status, choices.VENTER)

    def test_en_enhet_som_ikke_er_varslet_kan_ikke_stemple(self):
        o = self._oppdrag(self.a)
        with self.assertRaises(services.UlovligOvergang):
            services.sett_status(o, choices.RYKKER_UT, enhet=self.c)

    def test_gjeldende_for_enhet_er_bare_hennes(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(o, choices.FREMME, enhet=self.a)
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        for_b = Statusmelding.objects.gjeldende_for_enhet(services.koblingsrad(o, self.b))
        self.assertEqual([m.status for m in for_b], [choices.RYKKER_UT])
        self.assertEqual(len(Statusmelding.objects.gjeldende(o)), 3)

    def test_korreksjon_arver_koblingsrad_og_sted(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        services.sett_status(o, choices.FREMME, enhet=self.b)
        m = services.sett_status(o, choices.AVREIST, enhet=self.b, sted='sykehus')
        ny = services.korriger_tidspunkt(m, m.tidspunkt - timedelta(minutes=3), bruker=None)
        self.assertEqual(ny.oppdragsenhet, m.oppdragsenhet)
        self.assertEqual(ny.sted, 'sykehus')

    def test_automatisk_lukking_gjelder_enhetens_eget_paagaaende(self):
        """§4.3 per enhet: A rykker ut på nytt oppdrag, A's forrige lukkes — B's ikke."""
        felles = self._to_enheter()
        services.sett_status(felles, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(felles, choices.RYKKER_UT, enhet=self.b)
        nytt = self._oppdrag(self.a)
        services.start_oppdrag(nytt, enhet=self.a)
        felles.refresh_from_db()
        self.assertEqual(services.koblingsrad(felles, self.a).status, choices.LEDIG)
        self.assertEqual(services.koblingsrad(felles, self.b).status, choices.RYKKER_UT)
        self.assertEqual(felles.status, choices.RYKKER_UT)
        lukking = Statusmelding.objects.gjeldende_for_status(
            felles, choices.LEDIG, oppdragsenhet=services.koblingsrad(felles, self.a))
        self.assertTrue(lukking.automatisk)


class VarsleOgTaAvTests(FlereEnheterBasis):

    def test_varsle_legger_raden_sist_i_venter(self):
        o = self._oppdrag(self.a)
        rad = services.varsle_enhet(o, self.b)
        self.assertEqual(rad.status, choices.VENTER)
        self.assertGreater(rad.rekkefolge, o.primaer.rekkefolge)
        self.assertEqual(o.primaer.enhet, self.a)

    def test_samme_enhet_to_ganger_avvises(self):
        o = self._oppdrag(self.a)
        with self.assertRaises(ValueError):
            services.varsle_enhet(o, self.a)

    def test_varsle_henter_et_ferdig_oppdrag_tilbake_fra_historikken(self):
        o = self._oppdrag(self.a)
        services.sett_status(o, choices.RYKKER_UT)
        services.sett_status(o, choices.LEDIG)
        o.refresh_from_db()
        self.assertIsNotNone(o.historikk_fra)
        services.varsle_enhet(o, self.b)
        o.refresh_from_db()
        self.assertIsNone(o.historikk_fra)
        self.assertEqual(o.status, choices.VENTER)

    def test_ta_av_bare_mens_hun_venter(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        with self.assertRaises(ValueError):
            services.ta_av_enhet(o, self.b)
        services.ta_av_enhet(o, self.a)   # A venter fortsatt
        self.assertEqual([r.enhet for r in o.enheter.all()], [self.b])

    def test_den_siste_kan_ikke_tas_av(self):
        o = self._oppdrag(self.a)
        with self.assertRaises(ValueError):
            services.ta_av_enhet(o, self.a)
        self.assertEqual(o.enheter.count(), 1)

    def test_flytt_bytter_en_rad_og_holder_den_gamle_kolonnen_i_takt(self):
        o = self._to_enheter()
        bruker = _bruker('sentral', 'skriv_full')
        services.flytt_til_enhet(o, self.c, bruker=bruker, fra_enhet=self.b)
        self.assertEqual({r.enhet for r in o.enheter.all()}, {self.a, self.c})
        o.refresh_from_db()
        self.assertEqual(o.enhet, self.a, 'primær ble ikke flyttet')
        services.flytt_til_enhet(o, self.b, bruker=bruker, fra_enhet=self.a)
        o.refresh_from_db()
        self.assertEqual(o.enhet, self.b, 'primær flyttet — kolonnen følger')

    def test_flytt_til_en_enhet_som_alt_er_varslet_avvises(self):
        o = self._to_enheter()
        with self.assertRaises(ValueError):
            services.flytt_til_enhet(o, self.b, bruker=None, fra_enhet=self.a)


class EnhetensSynTests(FlereEnheterBasis):
    """Enhetsstatus og 30-minuttersvinduet måles per rad, ikke per oppdrag."""

    def test_enhetsstatus_er_hennes_egen(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        self.assertEqual(services.enhet_status(self.a)['status'], choices.RYKKER_UT)
        st_b = services.enhet_status(self.b)
        self.assertEqual(st_b['status'], choices.LEDIG)
        self.assertEqual(st_b['antall_ventende'], 1)

    def test_vinduet_maales_mot_bilens_egen_ledigmelding(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        services.sett_status(o, choices.LEDIG, enhet=self.a,
                             tidspunkt=timezone.now() - timedelta(minutes=45))
        self.assertNotIn(o, services.synlige_for_enhet(self.a))
        self.assertIn(o, services.synlige_for_enhet(self.b))

    def test_ventende_oppdrag_er_per_rad(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        self.assertEqual(list(services.ventende_oppdrag(self.b)), [o])
        self.assertEqual(list(services.ventende_oppdrag(self.a)), [])


class SerialiseringTests(FlereEnheterBasis):
    """§7.3: bilen ser hvem som er varslet, ikke deres status."""

    def test_varslede_er_de_andres_navn(self):
        from oppdrag.views_common import oppdrag_til_dict
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        d = oppdrag_til_dict(o, for_enhet=True, koblingsrad=services.koblingsrad(o, self.b))
        self.assertEqual(d['varslede'], ['Haugesund 56'])
        self.assertEqual(d['status'], choices.VENTER, 'B sin egen status, ikke oppdragets')
        self.assertEqual(d['neste_overgang'], choices.RYKKER_UT)

    def test_sentralbordet_faar_matrisen(self):
        from oppdrag.views_common import oppdrag_til_dict
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        d = oppdrag_til_dict(o)
        self.assertEqual(
            [(e['enhet_navn'], e['status']) for e in d['enheter']],
            [('Haugesund 56', choices.RYKKER_UT), ('Karmøy 12', choices.VENTER)])
        self.assertEqual(d['status'], choices.RYKKER_UT)


class EnhetskontoApiTests(FlereEnheterBasis):
    """Bil B er varslet i tillegg til A — hun stempler på sin egen rad."""

    def setUp(self):
        super().setUp()
        self.bil_b = _bruker('bil_b', 'skriv_handling')
        self.b.user = self.bil_b
        self.b.save()
        self.bil_c = _bruker('bil_c', 'skriv_handling')
        self.c.user = self.bil_c
        self.c.save()
        self.kb = _klient(self.bil_b)
        self.kc = _klient(self.bil_c)

    def test_lista_viser_oppdraget_med_hennes_status_og_de_andres_navn(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(o, choices.FREMME, enhet=self.a)
        res = self.kb.get('/oppdrag/api/oppdrag/')
        self.assertEqual(res.status_code, 200)
        rader = res.json()['data']
        self.assertEqual([r['id'] for r in rader], [o.pk])
        self.assertEqual(rader[0]['status'], choices.VENTER)
        self.assertEqual(rader[0]['varslede'], ['Haugesund 56'])
        self.assertEqual(rader[0]['statusmeldinger'], [], 'A sine meldinger er ikke hennes')

    def test_hun_stempler_paa_sin_egen_rad(self):
        o = self._to_enheter()
        res = self.kb.post(f'/oppdrag/api/oppdrag/{o.pk}/status/rykker_ut/',
                           content_type='application/json', data={})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['oppdrag']['status'], choices.RYKKER_UT)
        self.assertEqual(services.koblingsrad(o, self.b).status, choices.RYKKER_UT)
        self.assertEqual(services.koblingsrad(o, self.a).status, choices.VENTER)

    def test_detaljen_viser_bare_hennes_kjede(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        res = self.kb.get(f'/oppdrag/api/oppdrag/{o.pk}/')
        self.assertEqual(res.status_code, 200)
        d = res.json()['data']
        self.assertEqual(len(d['statusmeldinger']), 1)
        self.assertEqual(len(d['historikk']), 1)

    def test_en_bil_som_ikke_er_varslet_faar_403(self):
        o = self._to_enheter()
        self.assertEqual(self.kc.get(f'/oppdrag/api/oppdrag/{o.pk}/').status_code, 403)
        res = self.kc.post(f'/oppdrag/api/oppdrag/{o.pk}/status/rykker_ut/',
                           content_type='application/json', data={})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.kc.get('/oppdrag/api/oppdrag/').json()['data'], [])

    def test_grovsortering_settes_av_en_varslet_bil(self):
        o = self._to_enheter()
        res = self.kb.post(f'/oppdrag/api/oppdrag/{o.pk}/grovsortering/rod/',
                           content_type='application/json', data={})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['status'], choices.VENTER)


class BackupTests(FlereEnheterBasis):
    """Koblingsraden er med i dumpen, i FK-trygg rekkefølge."""

    def test_gjenoppretting_tar_med_koblingsradene(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        backup = create_backup(slug='oppdrag', kind=KIND_MANUAL)
        Oppdrag.objects.all().delete()
        self.assertEqual(Oppdragsenhet.objects.count(), 0)

        restore_backup(backup)

        o = Oppdrag.objects.get()
        self.assertEqual({r.enhet.navn: r.status for r in o.enheter.all()},
                         {'Haugesund 56': choices.VENTER, 'Karmøy 12': choices.RYKKER_UT})
        self.assertEqual(Statusmelding.objects.get().oppdragsenhet.enhet, self.b)


# ── Trinn 2: endepunktene og sentralbordets føring ──────────────────────────

class SentralbordBasis(FlereEnheterBasis):
    def setUp(self):
        super().setUp()
        self.sentral = _bruker('sentral', 'skriv_full')
        self.ks = _klient(self.sentral)

    def _gammelt(self, *enheter):
        """Et oppdrag opprettet for to timer siden — så en føring har rom
        mellom `created_at` og nå."""
        o = self._oppdrag(enheter[0] if enheter else self.a)
        for e in enheter[1:]:
            services.varsle_enhet(o, e)
        Oppdrag.objects.filter(pk=o.pk).update(
            created_at=timezone.now() - timedelta(hours=2))
        o.refresh_from_db()
        return o

    def _for(self, minutter):
        return timezone.now() - timedelta(minutes=minutter)


class OpprettMedFlereEnheterTests(SentralbordBasis):
    """`POST api/oppdrag/` tar `enhet_ider` — den første er primær (§4)."""

    def _kropp(self, **ekstra):
        return {'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt',
                'lokasjon_id': self.lokasjon.pk, **ekstra}

    def test_enhet_ider_gir_en_rad_per_enhet_i_rekkefolge(self):
        res = self.ks.post('/oppdrag/api/oppdrag/', content_type='application/json',
                           data=self._kropp(enhet_ider=[self.b.pk, self.a.pk, self.b.pk]))
        self.assertEqual(res.status_code, 200, res.content)
        o = Oppdrag.objects.get(pk=res.json()['data']['id'])
        self.assertEqual([r.enhet for r in o.enheter.all()], [self.b, self.a],
                         'dubletten strøket, rekkefølgen holdt')
        self.assertEqual(o.enhet, self.b, 'den første er primær')
        self.assertEqual([e['enhet_navn'] for e in res.json()['data']['enheter']],
                         ['Karmøy 12', 'Haugesund 56'])
        self.assertTrue(all(r.varslet_av == self.sentral for r in o.enheter.all()))

    def test_enhet_id_virker_fortsatt_og_betyr_en(self):
        res = self.ks.post('/oppdrag/api/oppdrag/', content_type='application/json',
                           data=self._kropp(enhet_id=self.a.pk))
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(len(res.json()['data']['enheter']), 1)

    def test_tom_liste_og_ukjent_enhet_avvises_uten_at_noe_opprettes(self):
        for ider in ([], [self.a.pk, 999999], ['x'], 'ikke-en-liste'):
            with self.subTest(ider=ider):
                res = self.ks.post('/oppdrag/api/oppdrag/', content_type='application/json',
                                   data=self._kropp(enhet_ider=ider))
                self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(Oppdrag.objects.count(), 0)

    def test_enhet_som_ikke_er_paa_vakt_avviser_hele_opprettelsen(self):
        self.b.pa_vakt = False
        self.b.save()
        res = self.ks.post('/oppdrag/api/oppdrag/', content_type='application/json',
                           data=self._kropp(enhet_ider=[self.a.pk, self.b.pk]))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Oppdrag.objects.count(), 0)


class VarsleOgTaAvEndepunktTests(SentralbordBasis):

    def _url(self, o, enhet):
        return f'/oppdrag/api/oppdrag/{o.pk}/enheter/{enhet.pk}/'

    def test_post_varsler_og_delete_tar_av(self):
        o = self._oppdrag(self.a)
        res = self.ks.post(self._url(o, self.b), content_type='application/json', data={})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual([e['enhet_navn'] for e in res.json()['data']['enheter']],
                         ['Haugesund 56', 'Karmøy 12'])
        res = self.ks.delete(self._url(o, self.b))
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual([e['enhet_navn'] for e in res.json()['data']['enheter']],
                         ['Haugesund 56'])

    def test_reglene_gir_400_med_forklaring(self):
        o = self._to_enheter()
        self.assertEqual(self.ks.post(self._url(o, self.b), content_type='application/json',
                                      data={}).status_code, 400, 'alt varslet')
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        res = self.ks.delete(self._url(o, self.b))
        self.assertEqual(res.status_code, 400)
        self.assertIn('meld ledig', res.json()['message'])
        self.ks.delete(self._url(o, self.a))
        self.assertEqual(self.ks.delete(self._url(o, self.b)).status_code, 400, 'den siste')

    def test_enhet_utenfor_vakt_kan_ikke_varsles(self):
        o = self._oppdrag(self.a)
        self.b.pa_vakt = False
        self.b.save()
        self.assertEqual(self.ks.post(self._url(o, self.b), content_type='application/json',
                                      data={}).status_code, 400)

    def test_gaten_er_skriv_full_og_ikke_enhetskonto(self):
        o = self._oppdrag(self.a)
        handling = _klient(_bruker('handling', 'skriv_handling'))
        self.assertEqual(handling.post(self._url(o, self.b), content_type='application/json',
                                       data={}).status_code, 403)
        bil = _bruker('bil_a', 'skriv_full')
        self.a.user = bil
        self.a.save()
        self.assertEqual(_klient(bil).post(self._url(o, self.b), content_type='application/json',
                                           data={}).status_code, 403)

    def test_ukjent_oppdrag_eller_enhet_er_404(self):
        o = self._oppdrag(self.a)
        self.assertEqual(self.ks.post(f'/oppdrag/api/oppdrag/999999/enheter/{self.b.pk}/',
                                      content_type='application/json', data={}).status_code, 404)
        self.assertEqual(self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/999999/',
                                      content_type='application/json', data={}).status_code, 404)


class FoeringTests(SentralbordBasis):
    """§9: sentralbordet fører en status bilen glemte — bakover i tid."""

    def _url(self, o, enhet, overgang, sted=None):
        u = f'/oppdrag/api/oppdrag/{o.pk}/enheter/{enhet.pk}/status/{overgang}/'
        return u + f'{sted}/' if sted else u

    def test_foering_lager_en_manuell_melding_paa_hennes_rad(self):
        o = self._gammelt(self.a, self.b)
        res = self.ks.post(self._url(o, self.b, 'rykker_ut'), content_type='application/json',
                           data={'tidspunkt': self._for(30).isoformat()})
        self.assertEqual(res.status_code, 200, res.content)
        m = Statusmelding.objects.get(oppdragsenhet__enhet=self.b)
        self.assertTrue(m.manuell)
        self.assertFalse(m.automatisk)
        self.assertEqual(m.meldt_av, self.sentral)
        self.assertEqual(services.koblingsrad(o, self.b).status, choices.RYKKER_UT)
        self.assertEqual(services.koblingsrad(o, self.a).status, choices.VENTER)
        self.assertTrue(res.json()['data']['melding']['manuell'])
        self.assertEqual(res.json()['data']['oppdrag']['status'], choices.RYKKER_UT)

    def test_tidspunkt_er_paakrevd(self):
        o = self._gammelt(self.a)
        for kropp in ({}, {'tidspunkt': ''}, {'tidspunkt': 'i går'}):
            with self.subTest(kropp=kropp):
                res = self.ks.post(self._url(o, self.a, 'rykker_ut'),
                                   content_type='application/json', data=kropp)
                self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(Statusmelding.objects.count(), 0)

    def test_overgangsreglene_gjelder_operatoren(self):
        o = self._gammelt(self.a)
        res = self.ks.post(self._url(o, self.a, 'fremme'), content_type='application/json',
                           data={'tidspunkt': self._for(30).isoformat()})
        self.assertEqual(res.status_code, 400)
        self.assertIn('Venter', res.json()['message'])

    def test_ikke_i_framtiden_ikke_foer_oppdraget_ikke_bak_siste(self):
        o = self._gammelt(self.a)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(60))
        for tid, feil in ((timezone.now() + timedelta(minutes=5), 'framtiden'),
                          (self._for(180), 'opprettet'),
                          (self._for(90), 'Rykker ut')):
            with self.subTest(feil=feil):
                res = self.ks.post(self._url(o, self.a, 'fremme'),
                                   content_type='application/json',
                                   data={'tidspunkt': tid.isoformat()})
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn(feil, res.json()['message'])

    def test_avreist_med_sted(self):
        o = self._gammelt(self.a)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(60))
        services.sett_status(o, choices.FREMME, tidspunkt=self._for(50))
        res = self.ks.post(self._url(o, self.a, 'avreist', 'sykehus'),
                           content_type='application/json',
                           data={'tidspunkt': self._for(40).isoformat()})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['melding']['sted_navn'], 'Sykehus')
        self.assertEqual(self.ks.post(self._url(o, self.a, 'fremme', 'sykehus'),
                                      content_type='application/json',
                                      data={'tidspunkt': self._for(40).isoformat()}
                                      ).status_code, 404)

    def test_ukjent_overgang_er_404_og_enhetskonto_403(self):
        o = self._gammelt(self.a)
        self.assertEqual(self.ks.post(self._url(o, self.a, 'flyr'),
                                      content_type='application/json',
                                      data={'tidspunkt': self._for(1).isoformat()}
                                      ).status_code, 404)
        bil = _bruker('bil_a', 'skriv_full')
        self.a.user = bil
        self.a.save()
        self.assertEqual(_klient(bil).post(self._url(o, self.a, 'rykker_ut'),
                                           content_type='application/json',
                                           data={'tidspunkt': self._for(1).isoformat()}
                                           ).status_code, 403)

    def test_ledig_fort_av_sentralen_rydder_naar_alle_er_ledige(self):
        o = self._gammelt(self.a, self.b)
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a, tidspunkt=self._for(60))
        services.sett_status(o, choices.LEDIG, enhet=self.a, tidspunkt=self._for(50))
        res = self.ks.post(self._url(o, self.b, 'ledig'), content_type='application/json',
                           data={'tidspunkt': self._for(40).isoformat()})
        self.assertEqual(res.status_code, 200, res.content)
        o.refresh_from_db()
        self.assertEqual(o.status, choices.LEDIG)
        self.assertIsNotNone(o.historikk_fra)


class GjenaapningTests(SentralbordBasis):
    """§9: «Ledig» tas tilbake som en korreksjon — innen 48 timer."""

    def _url(self, o, enhet):
        return f'/oppdrag/api/oppdrag/{o.pk}/enheter/{enhet.pk}/gjenaapne/'

    def _ferdig(self, o, enhet, ledig_for=10):
        services.sett_status(o, choices.RYKKER_UT, enhet=enhet, tidspunkt=self._for(60))
        services.sett_status(o, choices.FREMME, enhet=enhet, tidspunkt=self._for(50))
        services.sett_status(o, choices.LEDIG, enhet=enhet, tidspunkt=self._for(ledig_for))

    def test_gjenaapning_setter_raden_tilbake_der_den_sto(self):
        o = self._gammelt(self.a)
        self._ferdig(o, self.a)
        o.refresh_from_db()
        self.assertIsNotNone(o.historikk_fra)
        res = self.ks.post(self._url(o, self.a), content_type='application/json', data={})
        self.assertEqual(res.status_code, 200, res.content)
        rad = services.koblingsrad(o, self.a)
        self.assertEqual(rad.status, choices.FREMME)
        o.refresh_from_db()
        self.assertEqual(o.status, choices.FREMME)
        self.assertIsNone(o.historikk_fra, 'tilbake på tavla')
        # Korreksjonen peker på Ledig-meldingen, som blir stående som spor.
        ny = Statusmelding.objects.get(pk=res.json()['data']['melding']['id'])
        self.assertEqual(ny.korrigerer.status, choices.LEDIG)
        self.assertTrue(ny.manuell)
        self.assertIsNone(Statusmelding.objects.gjeldende_for_status(
            o, choices.LEDIG, oppdragsenhet=rad))
        # Fremme-tidspunktet flyttet seg ikke.
        fremme = Statusmelding.objects.gjeldende_for_status(o, choices.FREMME, oppdragsenhet=rad)
        self.assertEqual(fremme.tidspunkt, ny.tidspunkt)
        # Og operatøren kan føre videre derfra.
        res = self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.a.pk}/status/avreist/legevakt/',
                           content_type='application/json',
                           data={'tidspunkt': self._for(5).isoformat()})
        self.assertEqual(res.status_code, 200, res.content)

    def test_ledig_rett_fra_venter_gjenaapnes_til_venter(self):
        o = self._gammelt(self.a)
        services.sett_status(o, choices.LEDIG, tidspunkt=self._for(10))
        res = self.ks.post(self._url(o, self.a), content_type='application/json', data={})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(services.koblingsrad(o, self.a).status, choices.VENTER)

    def test_eldre_enn_48_timer_er_arkivets(self):
        o = self._gammelt(self.a)
        Oppdrag.objects.filter(pk=o.pk).update(created_at=timezone.now() - timedelta(days=3))
        self._ferdig(o, self.a, ledig_for=49 * 60)
        res = self.ks.post(self._url(o, self.a), content_type='application/json', data={})
        self.assertEqual(res.status_code, 400)
        self.assertIn('48 timer', res.json()['message'])
        self.assertEqual(services.koblingsrad(o, self.a).status, choices.LEDIG)

    def test_en_rad_som_ikke_er_ledig_kan_ikke_gjenaapnes(self):
        o = self._gammelt(self.a)
        res = self.ks.post(self._url(o, self.a), content_type='application/json', data={})
        self.assertEqual(res.status_code, 400)
        self.assertIn('ikke ledig', res.json()['message'])

    def test_bare_hennes_rad_gjenaapnes(self):
        o = self._gammelt(self.a, self.b)
        self._ferdig(o, self.a)
        self._ferdig(o, self.b)
        self.ks.post(self._url(o, self.b), content_type='application/json', data={})
        self.assertEqual(services.koblingsrad(o, self.a).status, choices.LEDIG)
        self.assertEqual(services.koblingsrad(o, self.b).status, choices.FREMME)


class FlyttEnRadTests(SentralbordBasis):

    def test_fra_enhet_id_velger_raden(self):
        o = self._to_enheter()
        res = self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/flytt/', content_type='application/json',
                           data={'enhet_id': self.c.pk, 'fra_enhet_id': self.b.pk})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual({r.enhet for r in o.enheter.all()}, {self.a, self.c})
        self.assertEqual(res.json()['data']['fra_enhet'], 'Karmøy 12')

    def test_uten_fra_enhet_id_er_det_den_primaere(self):
        o = self._to_enheter()
        self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/flytt/', content_type='application/json',
                     data={'enhet_id': self.c.pk})
        self.assertEqual([r.enhet for r in o.enheter.all()], [self.c, self.b])

    def test_til_en_som_alt_er_varslet_er_400(self):
        o = self._to_enheter()
        res = self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/flytt/', content_type='application/json',
                           data={'enhet_id': self.b.pk})
        self.assertEqual(res.status_code, 400)


class KorreksjonPerRadTests(SentralbordBasis):
    """`_naboer` måler mot bilens egne meldinger, ikke hele oppdragets."""

    def test_den_andre_bilens_meldinger_staar_ikke_i_veien(self):
        o = self._gammelt(self.a, self.b)
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a, tidspunkt=self._for(60))
        fremme = services.sett_status(o, choices.FREMME, enhet=self.a, tidspunkt=self._for(50))
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b, tidspunkt=self._for(45))
        # A's Fremme flyttes til etter B's Rykker ut — lovlig, B er ikke en nabo.
        services.valider_korreksjon(fremme, self._for(40))
        # Men ikke før A's eget Rykker ut.
        with self.assertRaises(services.KorreksjonUgyldig):
            services.valider_korreksjon(fremme, self._for(70))


class MatrisensTidspunktTests(SentralbordBasis):

    def test_status_tidspunkt_per_enhet(self):
        from oppdrag.views_common import oppdrag_til_dict
        o = self._gammelt(self.a, self.b)
        m = services.sett_status(o, choices.RYKKER_UT, enhet=self.b, tidspunkt=self._for(30))
        enheter = {e['enhet_navn']: e for e in oppdrag_til_dict(o)['enheter']}
        self.assertIsNone(enheter['Haugesund 56']['status_tidspunkt'])
        self.assertEqual(enheter['Karmøy 12']['status_tidspunkt'], m.tidspunkt.isoformat())

    def test_lista_koster_ikke_en_sporring_per_rad(self):
        for _ in range(3):
            self._to_enheter()
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as tre:
            self.ks.get('/oppdrag/api/oppdrag/')
        for _ in range(3):
            self._to_enheter()
        with CaptureQueriesContext(connection) as seks:
            self.ks.get('/oppdrag/api/oppdrag/')
        self.assertEqual(len(tre), len(seks))


class BilenSerDeAndreTests(TestCase):
    """Enhetsskjermen: «Også varslet: …» og «ført av sentralen»."""

    def setUp(self):
        from patients.js_test_utils import build_harness, node_available
        from oppdrag.tests_xss import EnhetEscapingOppforselTests
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(EnhetEscapingOppforselTests.HARNESS)
        self.stubb = EnhetEscapingOppforselTests.STUBB

    def _render(self, oppdrag, fn):
        import json
        from patients.js_test_utils import run_node
        return run_node(self.harness, self.stubb + f"""
            globalThis.mineOppdrag = [{json.dumps(oppdrag)}];
            const el = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: () => el }};
            {fn}();
            console.log(el.innerHTML);
        """)

    def _oppdrag(self, **ekstra):
        return {'id': 1, 'status': 'venter', 'status_navn': 'Venter',
                'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt',
                'lokasjon_navn': 'Scene', 'opprettet': '2026-08-29T20:00:00Z',
                'fritekst': '', 'neste_overgang': 'rykker_ut', 'neste_navn': 'Rykker ut',
                'statusmeldinger': [], 'varslede': [], **ekstra}

    def test_varslede_vises_som_navn_og_escapes(self):
        o = self._oppdrag(varslede=['KARM 12', '<b>x</b>'])
        ut = self._render(o, 'renderVentende')
        self.assertIn('Også varslet: KARM 12, &lt;b&gt;x&lt;/b&gt;', ut)
        o.update(status='fremme', status_navn='Fremme')
        self.assertIn('Også varslet: KARM 12', self._render(o, 'renderAktivt'))

    def test_uten_andre_staar_det_ingenting(self):
        ut = self._render(self._oppdrag(), 'renderVentende')
        self.assertNotIn('Også varslet', ut)

    def test_manuell_melding_merkes(self):
        o = self._oppdrag(status='fremme', status_navn='Fremme', statusmeldinger=[
            {'status': 'rykker_ut', 'status_navn': 'Rykker ut',
             'tidspunkt': '2026-08-29T20:05:00Z', 'manuell': True}])
        self.assertIn('ført av sentralen', self._render(o, 'renderAktivt'))
