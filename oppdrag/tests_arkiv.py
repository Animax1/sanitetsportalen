"""Vaktarkivet for oppdrag (fase 7).

Det som testes er det arkivet lover: at det fryser vakta slik den var, at
signaturen fanger en endring, at tallene er de samme som live viste, og at
kollapsen sletter radnivået uten å ta tallene med seg.
"""
import json
from datetime import timedelta

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from io import StringIO

from accounts.models import CustomUser, ModulTilgang
from core.arkiv import get_handler, kollaps, verifiser
from patients.models import Backup
from patients.services import vakt_for_year
from patients.test_helpers import sett_aktiv_vakt

from oppdrag import choices, services
from oppdrag.arkiv import OppdragArkivHandler, arkiver_vakt
from oppdrag.models import (
    ArkivertOppdrag, Enhet, Lokasjon, Oppdrag, OppdragArkiv,
)
from oppdrag.statistikk import arkiv_stats, oppdrag_stats

AAR = 2098


class ArkivBasis(TestCase):
    def setUp(self):
        self.vakt = sett_aktiv_vakt(AAR)
        self.lokasjon = Lokasjon.objects.create(navn='Hovedscene')
        self.enhet = Enhet.objects.create(navn='Haugesund 56', pa_vakt=True)
        self.admin = CustomUser.objects.create_superuser(
            username='arkivadmin', password='x', role='admin',
            must_change_password=False)
        self.naa = timezone.now()

    def _oppdrag(self, *, minutter_siden=60, **kwargs):
        felter = {
            'problemstilling': 'Pustevansker',
            'hastegrad': 'Akutt',
            'lokasjon': self.lokasjon,
            'enhet': self.enhet,
        }
        felter.update(kwargs)
        vakt = felter.pop('vakt', self.vakt)
        oppdrag = Oppdrag.objects.create(
            vakt=vakt, oppdragsnummer=services.neste_oppdragsnummer(vakt),
            **felter)
        Oppdrag.objects.filter(pk=oppdrag.pk).update(
            created_at=self.naa - timedelta(minutes=minutter_siden))
        oppdrag.refresh_from_db()
        return oppdrag

    def _stempel(self, oppdrag, status, minutter, *, automatisk=False):
        return services.sett_status(
            oppdrag, status, bruker=self.admin,
            tidspunkt=oppdrag.created_at + timedelta(minutes=minutter),
            automatisk=automatisk)

    def _full_vakt(self):
        """Et oppdrag gjennom hele kjeden, ett halvferdig, ett i historikken."""
        a = self._oppdrag()
        self._stempel(a, choices.RYKKER_UT, 2)
        self._stempel(a, choices.FREMME, 10)
        self._stempel(a, choices.AVREIST, 25)
        self._stempel(a, choices.LEVERER, 35)
        self._stempel(a, choices.LEDIG, 40)

        b = self._oppdrag(hastegrad='Vanlig', problemstilling='Kramper')
        self._stempel(b, choices.RYKKER_UT, 4)

        c = self._oppdrag(problemstilling='Brannskade', minutter_siden=200)
        self._stempel(c, choices.RYKKER_UT, 1)
        self._stempel(c, choices.FREMME, 6)
        self._stempel(c, choices.LEDIG, 20)
        return a, b, c


class ArkiveringTests(ArkivBasis):
    def test_arkivet_faar_vaktas_navn_og_antall(self):
        self._full_vakt()
        arkiv, antall = arkiver_vakt(self.vakt, 'Regnvær', self.admin)

        self.assertEqual(antall, 3)
        self.assertEqual(arkiv.antall_rader, 3)
        self.assertEqual(arkiv.vakt_navn, self.vakt.navn)
        self.assertEqual(arkiv.vakt_id, self.vakt.pk)
        self.assertEqual(arkiv.notat, 'Regnvær')
        self.assertIn(self.vakt.navn, arkiv.tittel)
        self.assertEqual(arkiv.importert_av_navn, 'arkivadmin')

    def test_navnene_fryses_som_tekst(self):
        """Enheten kan pensjoneres og lokasjonen fjernes — arkivet skal stå."""
        self._oppdrag()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)

        rad = arkiv.oppdrag.get()
        self.assertEqual(rad.enhet_navn, 'Haugesund 56')
        self.assertEqual(rad.lokasjon_navn, 'Hovedscene')

    def test_stemplingene_fryses_i_kolonner(self):
        a, _, _ = self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)

        rad = arkiv.oppdrag.get(oppdragsnummer=a.oppdragsnummer)
        self.assertEqual(rad.opprettet_at, a.created_at)
        self.assertEqual(rad.rykker_ut_at, a.created_at + timedelta(minutes=2))
        self.assertEqual(rad.fremme_at, a.created_at + timedelta(minutes=10))
        self.assertEqual(rad.ledig_at, a.created_at + timedelta(minutes=40))
        self.assertEqual(rad.sluttstatus, choices.LEDIG)

    def test_korreksjonen_er_det_som_fryses(self):
        """Radene bygges fra `gjeldende()` — originalen skal ikke arkiveres.

        Tidspunktet alene skiller ikke: en korreksjon lagres alltid etter
        raden den retter, så «siste rad per status» treffer den samme. Det er
        tellingene som avslører om originalen ble med — en overstyrt rad som
        var meldt forsinket, skal ikke telles én gang til.
        """
        oppdrag = self._oppdrag()
        self._stempel(oppdrag, choices.RYKKER_UT, 2)
        original = services.sett_status(
            oppdrag, choices.FREMME, bruker=self.admin,
            tidspunkt=oppdrag.created_at + timedelta(minutes=30),
            forsinket=True)
        services.korriger_tidspunkt(
            original, oppdrag.created_at + timedelta(minutes=9),
            bruker=self.admin)

        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        rad = arkiv.oppdrag.get()
        self.assertEqual(rad.fremme_at, oppdrag.created_at + timedelta(minutes=9))
        # Korreksjonen er meldt av et menneske ved et tastatur; originalen er
        # overstyrt. Ingen forsinket stempling står igjen.
        self.assertEqual(rad.antall_forsinket, 0)

    def test_automatisk_stempling_foelger_med(self):
        """Uten flagget ville §12.2-regelen falt bort i arkivet."""
        oppdrag = self._oppdrag()
        self._stempel(oppdrag, choices.RYKKER_UT, 2)
        self._stempel(oppdrag, choices.LEDIG, 30, automatisk=True)

        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        self.assertEqual(arkiv.oppdrag.get().automatiske_statuser, ['ledig'])

    def test_fritekst_arkiveres_ikke(self):
        """Feltet er unntatt verdilogging i audit — da skal det heller ikke
        fryses i 24 måneder i et arkiv."""
        self._oppdrag(fritekst='Noe operatøren skrev og angret på')
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)

        felter = {f.name for f in ArkivertOppdrag._meta.get_fields()}
        self.assertNotIn('fritekst', felter)
        rad_json = json.dumps(
            OppdragArkivHandler().rad_dicts(arkiv), ensure_ascii=False)
        self.assertNotIn('angret', rad_json)

    def test_oppdrag_i_historikken_arkiveres_ogsaa(self):
        """Historikk er rydding av tavla, ikke utmelding av vakta."""
        oppdrag = self._oppdrag()
        oppdrag.historikk_fra = timezone.now()
        oppdrag.save(update_fields=['historikk_fra'])

        _, antall = arkiver_vakt(self.vakt, '', self.admin)
        self.assertEqual(antall, 1)

    def test_bare_vaktas_oppdrag_arkiveres(self):
        self._oppdrag()
        self._oppdrag(vakt=vakt_for_year(2097))

        _, antall = arkiver_vakt(self.vakt, '', self.admin)
        self.assertEqual(antall, 1)

    def test_arkivering_rorer_ikke_oppdragene(self):
        """Frysing er en kopi. Tavla står som den sto."""
        self._full_vakt()
        arkiver_vakt(self.vakt, '', self.admin)
        self.assertEqual(Oppdrag.objects.filter(vakt=self.vakt).count(), 3)


class SignaturTests(ArkivBasis):
    def test_signaturen_settes_og_verifiserer(self):
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)

        self.assertEqual(len(arkiv.sha256), 64)
        self.assertFalse(verifiser(OppdragArkivHandler(), arkiv))

    def test_endret_rad_meldes_som_tukling(self):
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)

        rad = arkiv.oppdrag.first()
        rad.problemstilling = 'Noe annet'
        rad.save(update_fields=['problemstilling'])

        self.assertTrue(verifiser(OppdragArkivHandler(), arkiv))

    def test_slettet_rad_meldes_som_tukling(self):
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        arkiv.oppdrag.first().delete()

        self.assertTrue(verifiser(OppdragArkivHandler(), arkiv))

    def test_flyttet_tidspunkt_meldes_som_tukling(self):
        """Tidspunktene er hele grunnlaget for responstidene."""
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)

        rad = arkiv.oppdrag.exclude(fremme_at=None).first()
        rad.fremme_at = rad.fremme_at - timedelta(minutes=5)
        rad.save(update_fields=['fremme_at'])

        self.assertTrue(verifiser(OppdragArkivHandler(), arkiv))


class SignaturLaastTests(TestCase):
    """Låser signaturformen til literale verdier.

    Samme grep som `ArkivSignaturLaastTests` i pasientmodulen, og av samme
    grunn: endres feltnavn, sortering eller JSON-flagg, melder hvert arkiv
    tukling uten at noe er rørt. Formen er ny her — ingen arkiver finnes i
    prod ennå — men den låses fra første dag, ikke etter første klage.

    Feiler denne etter en refaktorering, er det refaktoreringen som er feil.
    """

    class _FakeArkiv:
        pk = 1
        vakt_navn = 'Testvakta'

    RADER = [
        {'oppdragsnummer': 2, 'enhet_navn': 'Karmøy 12', 'hastegrad': 'Vanlig'},
        {'oppdragsnummer': 1, 'enhet_navn': 'Haugesund 56', 'hastegrad': 'Akutt'},
    ]

    RAD_SHA = '8aec6a175b5432d4166e023203668ec2ce38acc17d8850785cbb9c52f4f0b0f7'
    AGGREGAT_SHA = 'cbf08fd66c96753d805e25e5606b370b6e2069c6627dd974952eaa4b68dc2e9d'

    def test_radsignaturen_er_uendret(self):
        from core.arkiv import beregn_sha256
        self.assertEqual(
            beregn_sha256(OppdragArkivHandler(), self._FakeArkiv(), self.RADER),
            self.RAD_SHA)

    def test_radsignaturen_er_uavhengig_av_radrekkefolge(self):
        """Radene sorteres på oppdragsnummer før hashing.

        Uten det ville en restore som gir radene i annen rekkefølge sett ut
        som tukling.
        """
        from core.arkiv import beregn_sha256
        self.assertEqual(
            beregn_sha256(OppdragArkivHandler(), self._FakeArkiv(),
                          list(reversed(self.RADER))),
            self.RAD_SHA)

    def test_aggregatsignaturen_er_uendret(self):
        from core.arkiv import beregn_aggregat_sha256
        self.assertEqual(
            beregn_aggregat_sha256(OppdragArkivHandler(), self._FakeArkiv(),
                                   {'full': {'summary': {'total': 2}}}),
            self.AGGREGAT_SHA)


class ArkivStatsMatcherTests(ArkivBasis):
    """Invarianten: arkivering endrer ikke tallene.

    Pasientmodulen har `StatsMatcher` for det samme. Uten den ville en
    arkivert vakt kunne vise andre tall enn den viste live, og forskjellen
    ville dukket opp først når noen sammenlignet i fjor med i år.
    """

    def test_arkivets_tall_er_de_samme_som_live(self):
        self._full_vakt()
        live = oppdrag_stats(self.vakt)
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        frosset = arkiv_stats(arkiv)

        # `enheter_pa_vakt` er beredskapen akkurat nå og finnes ikke for en
        # vakt som er over — alt annet skal stemme rad for rad.
        live_sum = dict(live['summary'])
        frosset_sum = dict(frosset['summary'])
        self.assertIsNone(frosset_sum.pop('enheter_pa_vakt'))
        live_sum.pop('enheter_pa_vakt')
        self.assertEqual(live_sum, frosset_sum)

        for nokkel in ('per_hastegrad', 'per_problemstilling', 'per_lokasjon',
                       'per_enhet', 'status_naa', 'responstid_per_hastegrad',
                       'responstid_per_enhet', 'oppdragstid_per_problemstilling',
                       'ankomster'):
            with self.subTest(nokkel=nokkel):
                self.assertEqual(live[nokkel], frosset[nokkel])

    def test_automatisk_regelen_gjelder_ogsaa_i_arkivet(self):
        """§12.2 følger med radene, ikke bare koden som leste dem live."""
        oppdrag = self._oppdrag()
        self._stempel(oppdrag, choices.RYKKER_UT, 2)
        self._stempel(oppdrag, choices.FREMME, 8)
        self._stempel(oppdrag, choices.LEDIG, 50, automatisk=True)

        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        sum_ = arkiv_stats(arkiv)['summary']
        self.assertEqual(sum_['oppdragstid']['n'], 0)
        self.assertEqual(sum_['utelatt']['automatisk'], 1)
        self.assertEqual(sum_['responstid']['median'], 8.0)


class KollapsTests(ArkivBasis):
    def test_kollaps_sletter_rader_og_beholder_tall(self):
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        foer = arkiv_stats(arkiv)

        slettet = kollaps(OppdragArkivHandler(), arkiv)

        self.assertEqual(slettet, 3)
        self.assertEqual(ArkivertOppdrag.objects.filter(arkiv=arkiv).count(), 0)
        self.assertTrue(arkiv.er_kollapset)
        self.assertEqual(arkiv.aggregat['full'], foer)

    def test_aggregatsignaturen_overtar_etter_kollaps(self):
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        kollaps(OppdragArkivHandler(), arkiv)

        self.assertFalse(verifiser(OppdragArkivHandler(), arkiv))

        arkiv.aggregat['full']['summary']['total'] = 99
        arkiv.save(update_fields=['aggregat'])
        self.assertTrue(verifiser(OppdragArkivHandler(), arkiv))

    def test_statistikk_endepunktet_leser_aggregatet_etter_kollaps(self):
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        foer = get_stats_via_registry(arkiv.pk)
        kollaps(OppdragArkivHandler(), arkiv)

        self.assertEqual(get_stats_via_registry(arkiv.pk), foer)


def get_stats_via_registry(pk):
    """Samme vei som statistikkappen går — gjennom `core.stats`."""
    from core.stats import get_handler as stats_handler
    return stats_handler('oppdrag').arkiv_full_stats(pk)


class KollapsKommandoTests(ArkivBasis):
    """Kommandoen går gjennom registeret og dekker begge arkivene."""

    def _kjor(self, **kwargs):
        ut = StringIO()
        call_command('kollaps_arkiv', stdout=ut, stderr=ut, **kwargs)
        return ut.getvalue()

    def _gammelt_arkiv(self):
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        OppdragArkiv.objects.filter(pk=arkiv.pk).update(
            importert_at=timezone.now() - timedelta(days=800))
        arkiv.refresh_from_db()
        return arkiv

    def _ta_arkiv_backup(self):
        Backup.objects.create(
            filename='oppdrag-arkiv.json.gz', kind='manual',
            module_slug='oppdrag_arkiv', size_bytes=1)

    def test_uten_backup_hoppes_arkivet_over(self):
        """Sperren: slettingen skal være gjenopprettbar."""
        arkiv = self._gammelt_arkiv()
        ut = self._kjor()

        self.assertIn('HOPPET OVER', ut)
        self.assertIn('oppdrag_arkiv', ut)
        arkiv.refresh_from_db()
        self.assertFalse(arkiv.er_kollapset)

    def test_med_backup_kollapses_arkivet(self):
        arkiv = self._gammelt_arkiv()
        self._ta_arkiv_backup()

        self._kjor()

        arkiv.refresh_from_db()
        self.assertTrue(arkiv.er_kollapset)
        self.assertEqual(ArkivertOppdrag.objects.count(), 0)

    def test_dry_run_sletter_ingenting(self):
        arkiv = self._gammelt_arkiv()
        self._ta_arkiv_backup()

        ut = self._kjor(dry_run=True)

        self.assertIn('Ville kollapset', ut)
        arkiv.refresh_from_db()
        self.assertFalse(arkiv.er_kollapset)
        self.assertEqual(ArkivertOppdrag.objects.count(), 3)

    def test_modulfilteret_lar_de_andre_staa(self):
        arkiv = self._gammelt_arkiv()
        self._ta_arkiv_backup()

        ut = self._kjor(modul='patients')

        self.assertNotIn('Kollapset «', ut)
        arkiv.refresh_from_db()
        self.assertFalse(arkiv.er_kollapset)

    def test_ukjent_modul_stopper_med_beskjed(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self._kjor(modul='finnesikke')

    def test_ferske_arkiv_rores_ikke(self):
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        self._ta_arkiv_backup()

        self._kjor()

        arkiv.refresh_from_db()
        self.assertFalse(arkiv.er_kollapset)


class RegistreringTests(TestCase):
    def test_arkivhandleren_er_registrert(self):
        handler = get_handler('oppdrag')
        self.assertIsNotNone(handler)
        self.assertEqual(handler.backup_slug, 'oppdrag_arkiv')
        self.assertEqual(handler.retention_dager, 730)

    def test_backuphandlerne_er_registrert(self):
        from core.backup import get_handler as backup_handler

        for slug in ('oppdrag', 'oppdrag_arkiv'):
            with self.subTest(slug=slug):
                self.assertIsNotNone(backup_handler(slug))

    def test_arkivbackupen_daekker_begge_modellene(self):
        """Et arkiv uten sine rader er ikke gjenopprettbart."""
        from core.backup import get_handler as backup_handler

        apps = backup_handler('oppdrag_arkiv').collect_apps()
        self.assertIn('oppdrag.OppdragArkiv', apps)
        self.assertIn('oppdrag.ArkivertOppdrag', apps)

    def test_oppdragsbackupen_utelater_arkivet(self):
        """Arkivet skal aldri endres av en restore av den aktive dataen."""
        from core.backup import get_handler as backup_handler

        ekskludert = backup_handler('oppdrag').collect_exclude()
        self.assertIn('oppdrag.OppdragArkiv', ekskludert)
        self.assertIn('oppdrag.ArkivertOppdrag', ekskludert)

    def test_hver_status_i_kjeden_har_en_arkivkolonne(self):
        """Legges en status til, må arkivet følge med.

        Uten denne ville en ny status blitt arkivert som ingenting, og
        tallene stille mistet et tidsledd.
        """
        from oppdrag.statistikk import _STATUSFELT

        felter = {f.name for f in ArkivertOppdrag._meta.get_fields()}
        for status, _ in choices.STATUS_VALG:
            if status == choices.VENTER:
                # `venter` settes ved oppretting og stemples aldri —
                # `opprettet_at` er tidspunktet.
                continue
            with self.subTest(status=status):
                self.assertIn(status, _STATUSFELT,
                              f'«{status}» mangler i _STATUSFELT')
                self.assertIn(_STATUSFELT[status], felter)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ArkivEndepunktTests(ArkivBasis):
    def _klient(self, bruker):
        c = Client()
        c.force_login(bruker)
        return c

    def _skriver(self):
        bruker = CustomUser.objects.create_user(
            username='skriver_arkiv', password='x', must_change_password=False)
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='oppdrag', nivaa='skriv_full')
        return bruker

    def test_admin_kan_arkivere(self):
        self._full_vakt()
        c = self._klient(self.admin)

        resp = c.post('/oppdrag/api/arkiv/',
                      data=json.dumps({'notat': 'Tørt og fint'}),
                      content_type='application/json')

        self.assertEqual(resp.status_code, 201)
        data = resp.json()['data']
        self.assertEqual(data['antall_oppdrag'], 3)
        self.assertEqual(OppdragArkiv.objects.count(), 1)

    def test_skriv_full_er_ikke_nok(self):
        """Arkivering starter en klokke mot en irreversibel sletting."""
        c = self._klient(self._skriver())
        for metode, sti in (('post', '/oppdrag/api/arkiv/'),
                            ('get', '/oppdrag/api/arkiv/')):
            with self.subTest(sti=sti):
                svar = getattr(c, metode)(sti, content_type='application/json')
                self.assertEqual(svar.status_code, 403)

    def test_liste_og_detalj_viser_arkivet(self):
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        c = self._klient(self.admin)

        liste = c.get('/oppdrag/api/arkiv/').json()['data']
        self.assertEqual(len(liste), 1)
        self.assertEqual(liste[0]['id'], arkiv.pk)

        detalj = c.get(f'/oppdrag/api/arkiv/{arkiv.pk}/').json()['data']
        self.assertFalse(detalj['tamper_detected'])
        self.assertEqual(detalj['stats']['summary']['total'], 3)

    def test_detaljvisningen_melder_tukling(self):
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        rad = arkiv.oppdrag.first()
        rad.hastegrad = 'Vanlig'
        rad.save(update_fields=['hastegrad'])

        detalj = self._klient(self.admin).get(
            f'/oppdrag/api/arkiv/{arkiv.pk}/').json()['data']
        self.assertTrue(detalj['tamper_detected'])

    def test_ukjent_arkiv_gir_404(self):
        resp = self._klient(self.admin).get('/oppdrag/api/arkiv/99999/')
        self.assertEqual(resp.status_code, 404)

    def test_sletting_krever_bekreftelse(self):
        self._oppdrag()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)
        c = self._klient(self.admin)

        resp = c.delete(f'/oppdrag/api/arkiv/{arkiv.pk}/',
                        data=json.dumps({}), content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(OppdragArkiv.objects.count(), 1)

        resp = c.delete(f'/oppdrag/api/arkiv/{arkiv.pk}/',
                        data=json.dumps({'confirm': True}),
                        content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(OppdragArkiv.objects.count(), 0)
        self.assertEqual(ArkivertOppdrag.objects.count(), 0)

    def test_arkivering_loggfores_i_audit(self):
        from audit.models import AuditLog

        self._oppdrag()
        self._klient(self.admin).post(
            '/oppdrag/api/arkiv/', data=json.dumps({}),
            content_type='application/json')

        self.assertTrue(AuditLog.objects.filter(
            table_name='oppdrag_oppdragarkiv', field_name='arkiv_lagret').exists())

    def test_statistikk_endepunktet_gir_arkivets_tall(self):
        """Fase 6 lovet at endepunktet ville virke når arkivet fantes."""
        self._full_vakt()
        arkiv, _ = arkiver_vakt(self.vakt, '', self.admin)

        resp = self._klient(self.admin).get(
            f'/statistikk/api/kilde/oppdrag/arkiv/{arkiv.pk}/full-stats/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['summary']['total'], 3)
