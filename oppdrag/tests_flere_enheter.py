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
    """§7.3: bilen ser hvem som er varslet; deres stempler kommer som
    `andre_meldinger` der lista bygges, ikke fra `oppdrag_til_dict`."""

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
        self.assertEqual(rader[0]['statusmeldinger'], [], 'A sine meldinger er ikke hennes kjede')
        # …men hun ser dem, med navn (§7.3 snudd 12. sep. 2026).
        self.assertEqual([(m['enhet_navn'], m['status']) for m in rader[0]['andre_meldinger']],
                         [('Haugesund 56', choices.RYKKER_UT), ('Haugesund 56', choices.FREMME)])

    def test_de_andres_stempler_er_med_i_etag(self):
        o = self._to_enheter()
        forste = self.kb.get('/oppdrag/api/oppdrag/')
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        andre = self.kb.get('/oppdrag/api/oppdrag/', HTTP_IF_NONE_MATCH=forste['ETag'])
        self.assertEqual(andre.status_code, 200, 'A sitt stempel skal ikke drukne i en 304')

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
        self.assertEqual([m['enhet_navn'] for m in d['andre_meldinger']], ['Haugesund 56'])

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

    def test_naa_avrundet_til_minuttet_godtas_rett_etter_opprettelsen(self):
        """`datetime-local` har minuttoppløsning: «nå» ned til minuttet ligger
        før et oppdrag opprettet sekunder tidligere, og skal likevel gå."""
        o = self._oppdrag(self.a)
        Oppdrag.objects.filter(pk=o.pk).update(created_at=timezone.now())
        tid = timezone.now().replace(second=0, microsecond=0)
        res = self.ks.post(self._url(o, self.a, 'rykker_ut'), content_type='application/json',
                           data={'tidspunkt': tid.isoformat()})
        self.assertEqual(res.status_code, 200, res.content)
        # Men ikke to minutter før.
        o2 = self._oppdrag(self.a)
        res = self.ks.post(self._url(o2, self.a, 'rykker_ut'), content_type='application/json',
                           data={'tidspunkt': (timezone.now() - timedelta(minutes=2)).isoformat()})
        self.assertEqual(res.status_code, 400)

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
        # Ledig-meldingen er borte (sporet ligger i revisjonsloggen), og
        # svaret er meldingen bak statusen raden står i nå.
        self.assertFalse(Statusmelding.objects.filter(oppdragsenhet=rad, status=choices.LEDIG).exists())
        fremme = Statusmelding.objects.gjeldende_for_status(o, choices.FREMME, oppdragsenhet=rad)
        self.assertEqual(res.json()['data']['melding']['id'], fremme.pk)
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
    """Enhetsskjermen: «Også varslet: …» og «endret av KO»."""

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

    def test_ogsaa_mens_hun_venter_ser_hun_de_andres_stempler(self):
        """André, 12. sep. 2026: «Bil B ser ikke A sine stempler så lenge den
        står i venter» — og det er nettopp da det er verdt å vite."""
        o = self._oppdrag(andre_meldinger=[
            {'status': 'rykker_ut', 'status_navn': 'Rykker ut', 'enhet_navn': 'HGSD 56',
             'tidspunkt': '2026-08-29T20:01:00Z'}])
        ut = self._render(o, 'renderVentende')
        self.assertIn('tidslinje-andre', ut)
        self.assertIn('HGSD 56:</span> Rykker ut', ut)
        # Uten andres stempler står det ingen tom tidslinje.
        self.assertNotIn('tidslinje-rad', self._render(self._oppdrag(), 'renderVentende'))

    def test_de_andres_stempler_staar_i_tidslinjen_med_navn_og_i_tidsrekkefolge(self):
        """André, 12. sep. 2026: «nyttig for de å vite historikken der»."""
        o = self._oppdrag(status='rykker_ut', status_navn='Rykker ut', statusmeldinger=[
            {'status': 'rykker_ut', 'status_navn': 'Rykker ut',
             'tidspunkt': '2026-08-29T20:05:00Z'}],
            andre_meldinger=[
            {'status': 'fremme', 'status_navn': 'Fremme', 'enhet_navn': '<b>HGSD 56</b>',
             'tidspunkt': '2026-08-29T20:09:00Z'},
            {'status': 'rykker_ut', 'status_navn': 'Rykker ut', 'enhet_navn': 'HGSD 56',
             'tidspunkt': '2026-08-29T20:01:00Z'}])
        ut = self._render(o, 'renderAktivt')
        self.assertIn('tidslinje-andre', ut)
        self.assertIn('&lt;b&gt;HGSD 56&lt;/b&gt;:', ut, 'navnet escapes')
        i_andres_rykker = ut.index('HGSD 56:</span> Rykker ut')
        i_egen = ut.index('<span>Rykker ut</span>')
        i_andres_fremme = ut.index('Fremme')
        self.assertLess(i_andres_rykker, i_egen, 'A rykket ut før B')
        self.assertLess(i_egen, i_andres_fremme, 'og var framme etter')
        # Egen kjede er urørt: B står i Rykker ut, ikke i A sin Fremme.
        self.assertIn('Rykker ut</span>', ut)

    def test_manuell_melding_merkes(self):
        o = self._oppdrag(status='fremme', status_navn='Fremme', statusmeldinger=[
            {'status': 'rykker_ut', 'status_navn': 'Rykker ut',
             'tidspunkt': '2026-08-29T20:05:00Z', 'manuell': True}])
        self.assertIn('endret av KO', self._render(o, 'renderAktivt'))


# ── Trinn 3: sentralbordets flater ──────────────────────────────────────────

class SentralbordetsMatriseTests(TestCase):
    """Matrisen i lista, avkryssingen, radene og knappene i detaljvisningen."""

    def setUp(self):
        from patients.js_test_utils import (
            OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        from .tests_runde_d import _konst
        self.harness = _konst(OPPDRAG_SENTRAL_JS, 'HASTEGRAD_REKKEFOLGE') + _konst(
            OPPDRAG_SENTRAL_JS, 'MANGLER_TRINN') + build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml', 'klokke')),
            (OPPDRAG_SENTRAL_JS, ('renderOppdrag', '_enhetsmatrise', '_grovMerke',
                                  'hastegradKlasse', 'tidSiden', 'mkEnhetsvalg',
                                  'mkEnhetsrader', '_enhetsknapper', '_varsleValg',
                                  '_lovligeOverganger', 'tidslinjeHtml', '_problemMedAntall', '_medAntall', '_grupperEnheter', '_typeRekkefolge', '_enhetskort',
                                  '_sorterOppdrag', '_manglerTrinn', '_manglerMinutter')),
        ))

    STUBB = ("globalThis.OPPDRAG_TILGANG = { kanSkrive: true };\n"
             "globalThis.STATUS_REKKEFOLGE = ['venter', 'rykker_ut', 'fremme',"
             " 'avreist', 'leverer', 'ledig'];\n"
             "globalThis.enheter = [{id: 1, navn: 'HGSD 56', pa_vakt: true},"
             " {id: 2, navn: 'KARM 12', pa_vakt: true}, {id: 3, navn: 'TYSV 3', pa_vakt: false}];\n")

    def _kjor(self, kode):
        from patients.js_test_utils import run_node
        return run_node(self.harness, self.STUBB + kode)

    OPPDRAG = ("{id: 7, nummer: 7, status: 'fremme', status_navn: 'Fremme',"
               " enhet_navn: 'HGSD 56', lokasjon_navn: 'Scene', problemstilling: 'Fall',"
               " hastegrad: 'Akutt', opprettet: '2026-08-28T20:00:00Z', fritekst: '',"
               " enheter: [{enhet_id: 1, enhet_navn: 'HGSD 56', status: 'fremme',"
               " status_navn: 'Fremme', status_tidspunkt: null},"
               " {enhet_id: 2, enhet_navn: '<b>KARM</b>', status: 'venter',"
               " status_navn: 'Venter', status_tidspunkt: null}]}")

    def test_lista_viser_en_brikke_per_enhet_og_escaper(self):
        ut = self._kjor(f"""
            globalThis.oppdragsliste = [{self.OPPDRAG}];
            const el = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: () => el }};
            renderOppdrag();
            console.log(el.innerHTML);
        """)
        self.assertEqual(ut.count('enhet-brikke'), 2)
        self.assertIn('status-venter', ut)
        self.assertIn('status-fremme', ut)
        self.assertIn('&lt;b&gt;KARM&lt;/b&gt;', ut)
        self.assertNotIn('<b>KARM</b>', ut)

    def test_uten_enheter_faller_brikken_tilbake_paa_toppnivaa(self):
        ut = self._kjor("""
            console.log(_enhetsmatrise({enhet_navn: 'E1', status: 'venter',
                                        status_navn: 'Venter', status_tidspunkt: null}));
        """)
        self.assertEqual(ut.count('enhet-brikke'), 1)
        self.assertIn('E1', ut)

    def test_avkryssingen_tar_bare_enheter_paa_vakt(self):
        ut = self._kjor("console.log(mkEnhetsvalg());")
        self.assertEqual(ut.count('type="checkbox"'), 2)
        self.assertIn('HGSD 56', ut)
        self.assertNotIn('TYSV 3', ut)

    def test_knappene_foelger_tilstanden(self):
        ut = self._kjor(f"console.log(mkEnhetsrader({self.OPPDRAG}));")
        self.assertEqual(ut.count('Endre status'), 2)
        self.assertEqual(ut.count('Ta av'), 1, 'bare den som venter')
        self.assertNotIn('Gjenåpne', ut)
        ledig = self._kjor("""
            console.log(mkEnhetsrader({enheter: [{enhet_id: 1, enhet_navn: 'A', status: 'ledig',
              status_navn: 'Ledig', status_tidspunkt: null}]}));
        """)
        self.assertIn('Gjenåpne', ledig)
        self.assertNotIn('Endre status', ledig)
        self.assertNotIn('Ta av', ledig)

    def test_den_siste_kan_ikke_tas_av_i_grensesnittet(self):
        ut = self._kjor("""
            console.log(mkEnhetsrader({enheter: [{enhet_id: 1, enhet_navn: 'A', status: 'venter',
              status_navn: 'Venter', status_tidspunkt: null}]}));
        """)
        self.assertNotIn('Ta av', ut)

    def test_uten_skrivetilgang_ingen_knapper(self):
        ut = self._kjor(f"""
            globalThis.OPPDRAG_TILGANG = {{ kanSkrive: false }};
            console.log(mkEnhetsrader({self.OPPDRAG}));
        """)
        for tekst in ('Endre status', 'Ta av', 'Gjenåpne', '<button'):
            self.assertNotIn(tekst, ut)

    def test_varslevalget_utelater_dem_som_alt_er_paa(self):
        ut = self._kjor(f"console.log(_varsleValg({self.OPPDRAG}));")
        self.assertNotIn('HGSD 56', ut)
        self.assertNotIn('TYSV 3', ut, 'ikke på vakt')
        # KARM 12 står alt på oppdraget som enhet 2 — ingen igjen å varsle.
        self.assertNotIn('Varsle enhet til', ut)
        ut = self._kjor("console.log(_varsleValg({id: 1, enheter: [{enhet_id: 1}]}));")
        self.assertIn('KARM 12', ut)
        self.assertIn('Varsle enhet til', ut)

    def test_lovlige_overganger_speiler_kjeden(self):
        ut = self._kjor("""
            console.log(JSON.stringify([
              _lovligeOverganger('venter'), _lovligeOverganger('leverer'),
              _lovligeOverganger('ledig')]));
        """)
        self.assertEqual(ut.splitlines()[0], '[["rykker_ut","ledig"],["ledig"],[]]')

    def test_tidslinjen_sier_hvem_bare_med_flere_enheter(self):
        melding = ("{id: 1, status: 'fremme', status_navn: 'Fremme', enhet_navn: 'KARM 12',"
                   " tidspunkt: '2026-08-28T20:00:00Z', manuell: true, meldt_av: '<i>ops</i>'}")
        to = self._kjor(f"""
            console.log(tidslinjeHtml({{historikk: [{melding}], enhetsbytter: [],
                                       enheter: [{{enhet_id: 1}}, {{enhet_id: 2}}]}}));
        """)
        self.assertIn('KARM 12: Fremme', to)
        self.assertIn('endret av KO (&lt;i&gt;ops&lt;/i&gt;)', to)
        en = self._kjor(f"""
            console.log(tidslinjeHtml({{historikk: [{melding}], enhetsbytter: [],
                                       enheter: [{{enhet_id: 2}}]}}));
        """)
        self.assertNotIn('KARM 12:', en)
        self.assertIn('Fremme', en)


class SentralsidenTests(SentralbordBasis):
    """Malen: avkryssingen og dataene til «Før status» følger skrivetilgangen."""

    def test_skriver_faar_avkryssing_og_stedene(self):
        res = self.ks.get('/oppdrag/')
        self.assertEqual(res.status_code, 200)
        html = res.content.decode()
        self.assertIn('id="nytt-enheter"', html)
        self.assertIn('window.OPPDRAG_AVREIST_TIL', html)
        self.assertIn('Sykehus', html)
        self.assertNotIn('id="nytt-enhet"', html, 'nedtrekket er borte')

    def test_leser_faar_ingen_avkryssing(self):
        leser = _klient(_bruker('leser', 'les'))
        html = leser.get('/oppdrag/').content.decode()
        self.assertNotIn('id="nytt-enheter"', html)

    def test_detaljen_navngir_enheten_bak_hver_melding(self):
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        d = self.ks.get(f'/oppdrag/api/oppdrag/{o.pk}/').json()['data']
        self.assertEqual([m['enhet_navn'] for m in d['historikk']], ['Karmøy 12'])


class InnlinjeskjemaeneTests(TestCase):
    """«Rett tid» og «Før status» bygger et skjema i raden med `innerHTML`.

    `trustedHtml()` pakker strengen inn i et objekt for `cellHtml()`; satt
    som innerHTML blir det «[object Object]». «Rett tid» sto slik fra fase 3
    til 11. sep. 2026 uten at noen test så det — ingen kjørte funksjonen.
    Her kjøres begge mot en minimal DOM-stubb, og skjemaet må være en streng
    med knappen i.
    """

    DOM = """
        globalThis.skjemaer = [];
        const rad = { querySelector: () => null, querySelectorAll: () => [], appendChild: (el) => skjemaer.push(el) };
        globalThis.document = {
          getElementById: (id) => (id.startsWith('tidslinje-rad-') || id.startsWith('enhet-rad-'))
            ? rad : { focus() {}, classList: { add() {}, remove() {} } },
          createElement: () => ({ _html: '', set innerHTML(v) { this._html = v; },
                                  get innerHTML() { return this._html; } }),
        };
        globalThis.window = { OPPDRAG_STATUS_NAVN: { rykker_ut: 'Rykker ut', ledig: 'Ledig' },
                              OPPDRAG_AVREIST_TIL: [['sykehus', 'Sykehus']] };
        globalThis.STATUS_REKKEFOLGE = ['venter', 'rykker_ut', 'fremme', 'avreist', 'leverer', 'ledig'];
        globalThis.apentOppdrag = { enheter: [{ enhet_id: 4, status: 'venter' }] };
    """

    def setUp(self):
        from patients.js_test_utils import (
            OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml')),
            (OPPDRAG_SENTRAL_JS, ('visRettTid', 'visFoerStatus', '_lovligeOverganger', '_lokalNaa')),
        ))

    def _skjema(self, kall):
        from patients.js_test_utils import run_node
        return run_node(self.harness, self.DOM + f"""
            {kall};
            const html = skjemaer[0].innerHTML;
            console.log(typeof html);
            console.log(html);
        """)

    def test_rett_tid_er_et_skjema_og_ikke_object_object(self):
        ut = self._skjema('visRettTid(5)')
        self.assertTrue(ut.startswith('string'), ut[:80])
        self.assertNotIn('[object Object]', ut)
        self.assertIn('data-action="lagreRettTid" data-id="5"', ut)

    def test_foer_status_tilbyr_de_lovlige_overgangene_og_stedene(self):
        ut = self._skjema('visFoerStatus(4)')
        self.assertTrue(ut.startswith('string'), ut[:80])
        self.assertNotIn('[object Object]', ut)
        self.assertIn('value="rykker_ut"', ut)
        self.assertIn('value="ledig"', ut)
        self.assertNotIn('value="fremme"', ut, 'ikke et ledd hun kan hoppe til')
        self.assertIn('Sykehus', ut)
        self.assertIn('data-action="lagreFoerStatus" data-id="4"', ut)


# ── Trinn 4: arkiv og statistikk ────────────────────────────────────────────

class ArkivOgStatistikkMedFlereEnheterTests(FlereEnheterBasis):
    """§5 A: én arkivrad per oppdrag × enhet, oppdrag telles distinkt,
    responstider per bil — og arkivet gir de samme tallene som live."""

    def setUp(self):
        super().setUp()
        self.admin = _bruker('adm', admin=True)

    def _for(self, minutter):
        return timezone.now() - timedelta(minutes=minutter)

    def _to_biler_paa_vei(self):
        o = self._to_enheter()
        Oppdrag.objects.filter(pk=o.pk).update(created_at=self._for(60))
        o.refresh_from_db()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a, tidspunkt=self._for(58))
        services.sett_status(o, choices.FREMME, enhet=self.a, tidspunkt=self._for(50))
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b, tidspunkt=self._for(55))
        services.sett_status(o, choices.FREMME, enhet=self.b, tidspunkt=self._for(40))
        services.sett_status(o, choices.LEDIG, enhet=self.b, tidspunkt=self._for(30))
        return o

    def test_arkivet_faar_en_rad_per_enhet_med_hennes_tider(self):
        from oppdrag.arkiv import arkiver_vakt
        from oppdrag.models import ArkivertOppdrag
        self._to_biler_paa_vei()
        arkiv, antall = arkiver_vakt(self.vakt, '', self.admin)
        self.assertEqual(antall, 2)
        self.assertEqual(arkiv.antall_rader, 2)
        rader = {r.enhet_navn: r for r in ArkivertOppdrag.objects.filter(arkiv=arkiv)}
        self.assertEqual(set(rader), {'Haugesund 56', 'Karmøy 12'})
        self.assertEqual(rader['Haugesund 56'].sluttstatus, choices.FREMME)
        self.assertEqual(rader['Karmøy 12'].sluttstatus, choices.LEDIG)
        self.assertIsNone(rader['Haugesund 56'].ledig_at)
        self.assertIsNotNone(rader['Karmøy 12'].ledig_at)
        self.assertNotEqual(rader['Haugesund 56'].fremme_at, rader['Karmøy 12'].fremme_at)

    def test_signaturen_verifiserer_og_er_uavhengig_av_radrekkefolge(self):
        from core.arkiv import beregn_sha256, verifiser
        from oppdrag.arkiv import OppdragArkivHandler, arkiver_vakt
        self._to_biler_paa_vei()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        handler = OppdragArkivHandler()
        self.assertFalse(verifiser(handler, arkiv))
        rader = handler.rad_dicts(arkiv)
        self.assertEqual(beregn_sha256(handler, arkiv, list(reversed(rader))), arkiv.sha256)

    def test_oppdrag_telles_distinkt_og_responstid_per_bil(self):
        from oppdrag.statistikk import oppdrag_stats
        self._to_biler_paa_vei()
        s = oppdrag_stats(self.vakt)
        self.assertEqual(s['summary']['total'], 1)
        self.assertEqual(s['summary']['enhetsinnsatser'], 2)
        self.assertEqual(s['summary']['aktive'], 1, 'A er fortsatt fremme')
        self.assertEqual(s['summary']['responstid']['n'], 2)
        self.assertEqual(s['summary']['responstid']['min'], 10.0)
        self.assertEqual(s['summary']['responstid']['max'], 20.0)
        self.assertEqual(dict(_flat(s['per_hastegrad'])), {'Akutt': 1}, 'ett oppdrag, ikke to')
        self.assertEqual(dict(_flat(s['per_enhet'])), {'Haugesund 56': 1, 'Karmøy 12': 1})
        status = {r['status']: r['antall'] for r in s['status_naa']}
        self.assertEqual(status[choices.FREMME], 1, 'oppdragets status er den mest aktive')
        self.assertEqual(status[choices.LEDIG], 0)
        self.assertEqual(sum(a['antall'] for a in s['ankomster']), 1)

    def test_arkivets_tall_er_de_samme_som_live(self):
        from oppdrag.arkiv import arkiver_vakt
        from oppdrag.statistikk import arkiv_stats, oppdrag_stats
        self._to_biler_paa_vei()
        annet = self._oppdrag(self.c)
        services.sett_status(annet, choices.RYKKER_UT, enhet=self.c)
        live = oppdrag_stats(self.vakt)
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        frosset = arkiv_stats(arkiv)
        live_sum = dict(live['summary']); live_sum.pop('enheter_pa_vakt')
        frosset_sum = dict(frosset['summary']); frosset_sum.pop('enheter_pa_vakt')
        self.assertEqual(live_sum, frosset_sum)
        for nokkel in ('per_hastegrad', 'per_problemstilling', 'per_lokasjon', 'per_enhet',
                       'status_naa', 'responstid_per_hastegrad', 'responstid_per_enhet',
                       'oppdragstid_per_problemstilling', 'ankomster'):
            with self.subTest(nokkel=nokkel):
                self.assertEqual(live[nokkel], frosset[nokkel])

    def test_arkivlista_teller_oppdrag_og_enhetsrader_hver_for_seg(self):
        from oppdrag.arkiv import arkiver_vakt
        self._to_biler_paa_vei()
        arkiver_vakt(self.vakt, '', self.admin)
        res = _klient(self.admin).get('/oppdrag/api/arkiv/')
        self.assertEqual(res.status_code, 200, res.content)
        rad = res.json()['data'][0]
        self.assertEqual((rad['antall_oppdrag'], rad['antall_enhetsrader']), (1, 2))


def _flat(fordeling):
    """`_sortert_synkende` gir en liste av par eller dicter — normaliser."""
    if isinstance(fordeling, dict):
        return list(fordeling.items())
    ut = []
    for post in fordeling:
        if isinstance(post, dict):
            ut.append((post.get('navn'), post.get('antall')))
        else:
            ut.append(tuple(post))
    return ut


class DetaljvinduetTegnesPaaNyttTests(TestCase):
    """Detaljvinduet tegnes på nytt etter «Ta av», «Varsle», «Før status» og
    «Rett tid» — mens det står åpent.

    André, 12. sep. 2026: «fjerner en bil eller gir en annen bil et oppdrag
    og du går ut av det vinduet så fryser appen.» `new bootstrap.Modal(el)`
    på et element som alt har en instans lager en ny, og `.show()` på den
    legger en bakgrunn til. Lukkingen fjerner bare den siste; de andre blir
    liggende over sida. Reprodusert med ekte Bootstrap 5.3.2: to bakgrunner
    igjen etter lukking. `getOrCreateInstance` gir den som finnes, og
    `.show()` på et åpent vindu er ingenting.
    """

    def setUp(self):
        from patients.js_test_utils import (
            OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml', 'klokke')),
            (OPPDRAG_SENTRAL_JS, ('visOppdrag', 'mkEnhetsrader', '_enhetsknapper', '_varsleValg',
                                  'tidslinjeHtml', 'hastegradKlasse', 'tidSiden')),
        ))

    STUBB = """
        globalThis.OPPDRAG_TILGANG = { kanSkrive: true };
        globalThis.enheter = [];
        globalThis.apentOppdrag = null;
        globalThis.apentOppdragId = null;
        globalThis.apiFetch = async () => ({ ok: true, json: async () => ({ status: 'ok', data: {
          id: 1, nummer: 1, problemstilling: 'Fall', hastegrad: 'Akutt', lokasjon_navn: 'Scene',
          status: 'venter', status_navn: 'Venter', fritekst: '', historikk_fra: null,
          enhet_navn: 'A', enheter: [{enhet_id: 1, enhet_navn: 'A', status: 'venter',
          status_navn: 'Venter', status_tidspunkt: null}], statusmeldinger: [], historikk: [],
          enhetsbytter: [] } }) });
        // Samme element for samme id, som i en ekte DOM — Bootstrap slår opp
        // instansen på elementet, og et nytt objekt per kall ville skjult feilen.
        const els = {};
        const el = () => ({ innerHTML: '', textContent: '', classList: { add() {}, remove() {} } });
        globalThis.document = { getElementById: (id) => (els[id] = els[id] || el()) };
        // Bootstrap 5 sin Modal, slik den oppfører seg: én instans per element via
        // getOrCreateInstance, og en ny konstruksjon teller som en instans til.
        let laget = 0; const instanser = new Map();
        class Modal {
          constructor(e) { laget++; this.e = e; this.vist = 0; }
          show() { this.vist++; }
          static getOrCreateInstance(e) {
            if (!instanser.has(e)) instanser.set(e, new Modal(e));
            return instanser.get(e);
          }
          static getInstance(e) { return instanser.get(e) || null; }
        }
        globalThis.bootstrap = { Modal };
        globalThis.antallLaget = () => laget;
    """

    def test_a_tegne_vinduet_paa_nytt_lager_ikke_en_ny_modal(self):
        from patients.js_test_utils import run_node
        run_node(self.harness, self.STUBB + """
            await visOppdrag(1);
            await visOppdrag(1);
            await visOppdrag(1);
            assert(antallLaget() === 1, 'forventet én modalinstans, fikk ' + antallLaget());
        """)


class StedOgGrovKnappeneTests(TestCase):
    """Klikkdelegeringen gjør `data-id` om til tall. Sted- og grovknappene
    bærer en nøkkel som er tekst, og må derfor bruke `data-arg` — ellers får
    handlingen NaN og gjør ingenting. Slik sto de i prod 12. sep. 2026
    («jeg får trykke knappen men kommer ikke videre»)."""

    def setUp(self):
        from patients.js_test_utils import (
            OPPDRAG_ENHET_JS, PORTAL_UTILS_JS, build_harness, node_available)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', '_handlerArgument')),
            (OPPDRAG_ENHET_JS, ('_stedvalg', '_grovsorteringsrad', '_kanGrovsortere')),
        ))

    STUBB = ("globalThis.AVREIST_TIL = [['sykehus','Sykehus'],['legevakt','Legevakt']];\n"
             "globalThis.GROVSORTERING = [['rod','Rød'],['gul','Gul'],['gronn','Grønn']];\n"
             # Det delegeringen ser: dataset-attributtene på knappen i markupen.
             "function datasetFra(html, id) {\n"
             "  const m = html.match(new RegExp('<button[^>]*id=\"' + id + '\"[^>]*>'));\n"
             "  const ds = {}; for (const [, k, v] of m[0].matchAll(/data-([a-z]+)=\"([^\"]*)\"/g)) ds[k] = v;\n"
             "  return { dataset: ds };\n"
             "}\n")

    def test_argumentet_er_nokkelen(self):
        from patients.js_test_utils import run_node
        run_node(self.harness, self.STUBB + """
            const sted = _handlerArgument(datasetFra(_stedvalg(), 'stemple-sted-sykehus'));
            assert(sted === 'sykehus', 'stedknappen gir ' + JSON.stringify(sted));
            const grov = _handlerArgument(datasetFra(_grovsorteringsrad({grovsortering: ''}), 'grov-gul'));
            assert(grov === 'gul', 'grovknappen gir ' + JSON.stringify(grov));
        """)

    def test_grovsortering_finnes_fra_fremme(self):
        from patients.js_test_utils import run_node
        run_node(self.harness, self.STUBB + """
            assert(!_kanGrovsortere({status: 'venter'}) && !_kanGrovsortere({status: 'rykker_ut'}), 'ikke før fremme');
            assert(_kanGrovsortere({status: 'fremme'}) && _kanGrovsortere({status: 'avreist'}) && _kanGrovsortere({status: 'leverer'}), 'fra fremme');
        """)


# ── Andrés rapport 2 (12. sep. 2026) ─────────────────────────────────────────

class RapportToOppdragTests(SentralbordBasis):

    def test_naa_rundet_til_minuttet_er_ikke_framtid_selv_om_klokka_gaar_foran(self):
        """Nettleserens «nå» kan ligge sekunder foran serverens; rundet til
        minuttet lå det i framtiden for serveren."""
        o = self._gammelt(self.a)
        tid = timezone.now().replace(second=0, microsecond=0) + timedelta(seconds=40)
        res = self.ks.post(self._url_status(o, self.a, 'rykker_ut'), content_type='application/json',
                           data={'tidspunkt': tid.isoformat()})
        self.assertEqual(res.status_code, 200, res.content)
        res = self.ks.post(self._url_status(o, self.a, 'fremme'), content_type='application/json',
                           data={'tidspunkt': (timezone.now() + timedelta(minutes=3)).isoformat()})
        self.assertEqual(res.status_code, 400)

    def _url_status(self, o, enhet, overgang):
        return f'/oppdrag/api/oppdrag/{o.pk}/enheter/{enhet.pk}/status/{overgang}/'

    def test_ta_av_den_siste_ventende_rydder_til_historikken(self):
        """A meldte ledig, B ble tatt av mens hun ventet — da er oppdraget ferdig."""
        o = self._to_enheter()
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(o, choices.LEDIG, enhet=self.a)
        o.refresh_from_db()
        self.assertIsNone(o.historikk_fra, 'B venter fortsatt')
        res = self.ks.delete(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.b.pk}/')
        self.assertEqual(res.status_code, 200, res.content)
        o.refresh_from_db()
        self.assertEqual(o.status, choices.LEDIG)
        self.assertIsNotNone(o.historikk_fra)
        # Og sporet står i tidslinjen.
        d = self.ks.get(f'/oppdrag/api/oppdrag/{o.pk}/').json()['data']
        self.assertEqual([(h['type'], h['enhet_navn'], h['av']) for h in d['enhetshendelser']],
                         [('tatt_av', 'Karmøy 12', 'sentral')])
        self.assertTrue(all(e['varslet_at'] for e in d['enheter']))

    def test_angre_tar_siste_status_tilbake(self):
        o = self._gammelt(self.a)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(60))
        services.sett_status(o, choices.FREMME, tidspunkt=self._for(50))
        m = services.sett_status(o, choices.AVREIST, tidspunkt=self._for(40), sted='sykehus')
        res = self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.a.pk}/angre/')
        self.assertEqual(res.status_code, 200, res.content)
        rad = services.koblingsrad(o, self.a)
        self.assertEqual(rad.status, choices.FREMME)
        self.assertFalse(Statusmelding.objects.filter(pk=m.pk).exists(), 'Avreist-meldingen er borte')
        self.assertEqual(res.json()['data']['melding']['status'], choices.FREMME)
        # Angre helt tilbake til Venter.
        self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.a.pk}/angre/')
        res = self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.a.pk}/angre/')
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()['data']['melding'], 'Venter har ingen melding')
        self.assertEqual(services.koblingsrad(o, self.a).status, choices.VENTER)
        res = self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.a.pk}/angre/')
        self.assertEqual(res.status_code, 400)

    def test_angre_tar_med_rettingshistorikken_og_sletter_gjennom_korreksjoner(self):
        """En status som er rettet («Rett tid») har to rader; angre tar begge —
        ellers ble den gamle gjeldende igjen. Og et oppdrag med korreksjoner
        kan slettes."""
        o = self._gammelt(self.a)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(60))
        f = services.sett_status(o, choices.FREMME, tidspunkt=self._for(50))
        services.korriger_tidspunkt(f, self._for(48), bruker=self.sentral)
        self.assertEqual(self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.a.pk}/angre/').status_code, 200)
        self.assertEqual(services.koblingsrad(o, self.a).status, choices.RYKKER_UT)
        self.assertFalse(Statusmelding.objects.filter(oppdragsenhet__enhet=self.a, status=choices.FREMME).exists())
        r = Statusmelding.objects.get(oppdragsenhet__enhet=self.a)
        services.korriger_tidspunkt(r, self._for(61), bruker=self.sentral)
        self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.a.pk}/angre/')
        res = self.ks.delete(f'/oppdrag/api/oppdrag/{o.pk}/', content_type='application/json',
                             data={'confirm': True})
        self.assertEqual(res.status_code, 200, res.content)

    def test_sentralbordet_sletter_bare_mens_alle_venter(self):
        o = self._to_enheter()
        d = self.ks.get(f'/oppdrag/api/oppdrag/{o.pk}/').json()['data']
        self.assertTrue(d['kan_slettes'])
        services.sett_status(o, choices.RYKKER_UT, enhet=self.b)
        self.assertFalse(self.ks.get(f'/oppdrag/api/oppdrag/{o.pk}/').json()['data']['kan_slettes'])
        res = self.ks.delete(f'/oppdrag/api/oppdrag/{o.pk}/', content_type='application/json',
                             data={'confirm': True})
        self.assertEqual(res.status_code, 403)
        # Angre B tilbake til Venter — da kan det slettes, med bekreftelse.
        self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.b.pk}/angre/')
        self.assertEqual(self.ks.delete(f'/oppdrag/api/oppdrag/{o.pk}/', content_type='application/json',
                                        data={}).status_code, 400, 'bekreftelse mangler')
        res = self.ks.delete(f'/oppdrag/api/oppdrag/{o.pk}/', content_type='application/json',
                             data={'confirm': True})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(Oppdrag.objects.filter(pk=o.pk).exists())

    def test_global_admin_sletter_i_historikken_enkeltvis_og_alt(self):
        adm = _klient(_bruker('adm', admin=True))
        ferdig = []
        for _ in range(2):
            o = self._oppdrag(self.a)
            services.sett_status(o, choices.RYKKER_UT)
            services.sett_status(o, choices.LEDIG)
            ferdig.append(o)
        aktivt = self._oppdrag(self.a)
        services.sett_status(aktivt, choices.RYKKER_UT)
        # Sentralbordet får ikke slette i historikken; admin får.
        self.assertEqual(self.ks.delete(f'/oppdrag/api/oppdrag/{ferdig[0].pk}/',
                                        content_type='application/json',
                                        data={'confirm': True}).status_code, 403)
        self.assertEqual(adm.delete(f'/oppdrag/api/oppdrag/{ferdig[0].pk}/',
                                    content_type='application/json',
                                    data={'confirm': True}).status_code, 200)
        self.assertEqual(self.ks.delete('/oppdrag/api/historikk/', content_type='application/json',
                                        data={'confirm': True}).status_code, 403)
        res = adm.delete('/oppdrag/api/historikk/', content_type='application/json',
                         data={'confirm': True})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(set(Oppdrag.objects.values_list('pk', flat=True)), {aktivt.pk},
                         'det aktive oppdraget står')

    def test_stedet_er_med_i_matrisen_og_paa_enhetskortet(self):
        o = self._gammelt(self.a)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(60))
        services.sett_status(o, choices.FREMME, tidspunkt=self._for(50))
        services.sett_status(o, choices.AVREIST, tidspunkt=self._for(40), sted='sykehus')
        rad = self.ks.get('/oppdrag/api/oppdrag/').json()['data'][0]
        self.assertEqual(rad['enheter'][0]['sted_navn'], 'Sykehus')
        kort = next(e for e in self.ks.get('/oppdrag/api/enheter/').json()['data'] if e['id'] == self.a.pk)
        self.assertEqual(kort['sted_navn'], 'Sykehus')


class TidslinjeMedVarsletOgAngreTests(TestCase):
    def setUp(self):
        from patients.js_test_utils import (
            OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
            (OPPDRAG_SENTRAL_JS, ('tidslinjeHtml',)),
        ))

    def test_varslet_tatt_av_og_angre_paa_siste(self):
        from patients.js_test_utils import run_node
        ut = run_node(self.harness, """
            globalThis.OPPDRAG_TILGANG = { kanSkrive: true };
            console.log(tidslinjeHtml({
              opprettet: '2026-08-28T20:00:00Z',
              enheter: [{enhet_id: 1, enhet_navn: 'HGSD 56', varslet_at: '2026-08-28T20:00:00Z'},
                        {enhet_id: 2, enhet_navn: '<b>KARM</b>', varslet_at: '2026-08-28T20:05:00Z'}],
              enhetshendelser: [{id: 1, type: 'tatt_av', enhet_navn: '<b>KARM</b>',
                                 tidspunkt: '2026-08-28T20:10:00Z', av: 'adm'}],
              historikk: [
                {id: 1, enhet_id: 1, status: 'rykker_ut', status_navn: 'Rykker ut', tidspunkt: '2026-08-28T20:02:00Z'},
                {id: 2, enhet_id: 1, status: 'fremme', status_navn: 'Fremme', tidspunkt: '2026-08-28T20:08:00Z'}],
              enhetsbytter: []}));
        """)
        self.assertIn('Varslet: HGSD 56', ut)
        self.assertIn('Varslet: &lt;b&gt;KARM&lt;/b&gt;', ut)
        self.assertIn('Tatt av: &lt;b&gt;KARM&lt;/b&gt;', ut)
        self.assertEqual(ut.count('data-action="angreStatus"'), 1, 'bare siste melding kan angres')
        self.assertIn('data-action="angreStatus" data-id="1"', ut)
        self.assertLess(ut.index('Rykker ut'), ut.index('Fremme'))
