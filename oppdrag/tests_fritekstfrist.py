"""Fristen på oppdragets frie tekst (10. okt. 2026, A.12).

André: «C, 3 dager» — klokka går fra **siste aktivitet** på oppdraget, ikke fra
`historikk_fra`, slik at et oppdrag som står med «trenger ny ressurs» også får
en frist. Se `oppdrag/fritekstfrist.py`.

Testene går gjennom de ekte endepunktene for vis-regelen og gjennom
`purge_old_logs` for feiingen: en test som bare spurte `er_utlopt()` ville gått
grønn om kallstedet i `oppdrag_til_dict` forsvant — og det er det som står
mellom teksten og den som åpner historikken.

**Aldringen er generisk med vilje.** `_eldes()` flytter *hvert* tidsstempel på
oppdraget og alle radene som peker på det, og bruker ikke `_kilder()` fra
modulen under test. Ellers ville en kilde som falt ut av lista også falt ut av
fiksturen, og testen av kilden ville målt ingenting.
"""
import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.db.models import DateTimeField, F
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.models import AppSetting
from oppdrag import fritekstfrist, services
from oppdrag.models import (
    Enhet, Enhetsbytte, Enhetshendelse, Lokasjon, Oppdrag, Oppdragsendring, Oppdragsenhet,
    Statusmelding,
)
from patients.js_test_utils import (
    OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available, run_node,
)

AAR = 2026
NOTAT = 'Pasienten heter Kari, bor i Storgata 5'
STED = 'Storgata 5'


def _eldes(oppdrag, dager):
    """Flytt hvert tidsstempel på oppdraget og radene under det `dager` bakover."""
    delta = timedelta(days=dager)
    for modell, filter_ in ((Oppdrag, {'pk': oppdrag.pk}),
                            (Statusmelding, {'oppdrag': oppdrag}),
                            (Oppdragsenhet, {'oppdrag': oppdrag}),
                            (Oppdragsendring, {'oppdrag': oppdrag}),
                            (Enhetshendelse, {'oppdrag': oppdrag}),
                            (Enhetsbytte, {'oppdrag': oppdrag})):
        felt = {f.name: F(f.name) - delta for f in modell._meta.get_fields()
                if isinstance(f, DateTimeField)}
        modell.objects.filter(**filter_).update(**felt)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class FristBasis(TestCase):

    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        self.vakt = sett_aktiv_vakt(AAR)
        self.lokasjon = Lokasjon.objects.create(navn='Hovedscene')
        self.bil = Enhet.objects.create(navn='Haugesund 56')
        self.bil2 = Enhet.objects.create(navn='Haugesund 57')
        self.operator = CustomUser.objects.create_user(
            username='ko_frist', password='x', must_change_password=False)
        ModulTilgang.objects.create(bruker=self.operator, modul_slug='oppdrag', nivaa='skriv_full')
        self.klient = Client()
        self.klient.force_login(self.operator)

    def _oppdrag(self, *, fritekst=NOTAT, sted_tekst=STED, historikk=False):
        o = Oppdrag.objects.create(
            vakt=self.vakt, enhet=self.bil, problemstilling='Udefinert',
            hastegrad='Haster', lokasjon=self.lokasjon, fritekst=fritekst,
            oppdragsnummer=services.neste_oppdragsnummer(self.vakt))
        if sted_tekst:
            # Bilen står i «Avreist → Annet sted»: raden og meldingen sier det samme.
            o.enheter.update(status='avreist')
            Statusmelding.objects.create(
                oppdrag=o, oppdragsenhet=o.enheter.first(), status='avreist',
                tidspunkt=timezone.now(), sted='annet', sted_tekst=sted_tekst)
        if historikk:
            Oppdrag.objects.filter(pk=o.pk).update(historikk_fra=timezone.now())
        return o

    def _detalj(self, o):
        return self.klient.get(f'/oppdrag/api/oppdrag/{o.pk}/').json()['data']


class RegelenTests(TestCase):

    def test_grensa(self):
        """Ved grensa er teksten borte — `slettes_at` er når den forsvinner."""
        siste = timezone.now()
        frist = siste + timedelta(days=3)
        self.assertFalse(fritekstfrist.er_utlopt(siste, frist - timedelta(seconds=1), 3))
        self.assertTrue(fritekstfrist.er_utlopt(siste, frist, 3))
        self.assertFalse(fritekstfrist.er_utlopt(None, frist, 3), 'uten klokke, ingen frist')

    def test_fristen_er_tre_dager_og_klemmes(self):
        self.assertEqual(fritekstfrist.frist_dager(), 3)
        for lagret, ventet in (('0', 1), ('-5', 1), ('999', 30), ('tull', 3), ('7', 7)):
            with self.subTest(lagret=lagret):
                AppSetting.set(fritekstfrist.DAGER_NOKKEL, lagret)
                self.assertEqual(fritekstfrist.frist_dager(), ventet)


class KlokkaTests(FristBasis):
    """Hver slags aktivitet flytter klokka — også på et oppdrag som aldri når
    historikken. Kildene står her for hånd, ikke lest fra modulen."""

    def _er_utlopt(self, o):
        o = Oppdrag.objects.get(pk=o.pk)    # ingen husket annotasjon
        return fritekstfrist.tekst_utlopt(o)

    def test_gammelt_oppdrag_uten_aktivitet_er_utlopt(self):
        o = self._oppdrag()
        self.assertFalse(self._er_utlopt(o))
        _eldes(o, 4)
        self.assertTrue(self._er_utlopt(o))

    def test_trenger_ny_ressurs_faar_ogsaa_en_frist(self):
        """Hullet valg A ville latt stå: oppdraget kommer aldri til historikken."""
        o = self._oppdrag()
        Oppdrag.objects.filter(pk=o.pk).update(trenger_ressurs=True,
                                               trenger_ressurs_siden=timezone.now())
        _eldes(o, 4)
        self.assertIsNone(Oppdrag.objects.get(pk=o.pk).historikk_fra)
        self.assertTrue(self._er_utlopt(o))

    def test_hver_aktivitet_starter_klokka_paa_nytt(self):
        naa = timezone.now
        aktiviteter = {
            'ny stempling': lambda o: Statusmelding.objects.create(
                oppdrag=o, oppdragsenhet=o.enheter.first(), status='fremme', tidspunkt=naa()),
            'tilbaketrukket stempling': lambda o: Statusmelding.objects.filter(
                oppdrag=o).first().save(),
            'endret verdi': lambda o: Oppdragsendring.objects.create(
                oppdrag=o, felt=Oppdragsendring.NOTAT),
            'ny enhet varslet': lambda o: Oppdragsenhet.objects.create(
                oppdrag=o, enhet=self.bil2, varslet_at=naa()),
            'enhetshendelse': lambda o: Enhetshendelse.objects.create(
                oppdrag=o, enhet=self.bil, type=Enhetshendelse.AVVENTER),
            'enhetsbytte': lambda o: Enhetsbytte.objects.create(
                oppdrag=o, fra_enhet=self.bil, til_enhet=self.bil2),
            'flyttet til historikk': lambda o: Oppdrag.objects.filter(pk=o.pk).update(
                historikk_fra=naa()),
            'lagret på raden (grovsortering)': lambda o: Oppdrag.objects.get(pk=o.pk).save(),
        }
        for navn, gjor in aktiviteter.items():
            with self.subTest(navn):
                o = self._oppdrag()
                _eldes(o, 4)
                self.assertTrue(self._er_utlopt(o))
                gjor(o)
                self.assertFalse(self._er_utlopt(o), f'«{navn}» flyttet ikke klokka')


class VisRegelenTests(FristBasis):
    """Gjennom endepunktene KO faktisk leser."""

    def test_tavla_skjuler_notat_og_annet_sted_naar_fristen_er_ute(self):
        o = self._oppdrag()
        rad = self.klient.get('/oppdrag/api/oppdrag/').json()['data'][0]
        self.assertEqual(rad['fritekst'], NOTAT)
        self.assertIn(STED, rad['enheter'][0]['sted_navn'])
        _eldes(o, 4)
        rad = self.klient.get('/oppdrag/api/oppdrag/').json()['data'][0]
        self.assertEqual(rad['fritekst'], '')
        self.assertIsNone(rad['fritekst_slettes'])
        self.assertNotIn(STED, rad['enheter'][0]['sted_navn'])
        self.assertEqual(rad['enheter'][0]['sted_navn'], 'Annet sted')

    def test_historikken(self):
        o = self._oppdrag(historikk=True)
        self.assertEqual(self.klient.get('/oppdrag/api/historikk/').json()['data'][0]['fritekst'], NOTAT)
        _eldes(o, 4)
        self.assertEqual(self.klient.get('/oppdrag/api/historikk/').json()['data'][0]['fritekst'], '')

    def test_detaljvinduet_og_tidslinjen(self):
        o = self._oppdrag()
        _eldes(o, 4)
        data = self._detalj(o)
        self.assertEqual(data['fritekst'], '')
        for liste in ('statusmeldinger', 'historikk'):
            for m in data[liste]:
                with self.subTest(liste=liste, status=m['status']):
                    self.assertEqual(m['sted_tekst'], '')
                    self.assertNotIn(STED, m['sted_navn'])

    def test_nedtellingen_er_et_fast_tidspunkt_og_bare_naar_det_staar_tekst(self):
        o = self._oppdrag()
        siste = fritekstfrist.frist_for(Oppdrag.objects.get(pk=o.pk))[0]
        data = self._detalj(o)
        self.assertEqual(data['fritekst_slettes'], (siste + timedelta(days=3)).isoformat())
        uten = self._oppdrag(fritekst='', sted_tekst='')
        self.assertIsNone(self._detalj(uten)['fritekst_slettes'])

    def test_aa_skrive_et_nytt_notat_starter_klokka_paa_nytt(self):
        """Gjennom den ekte PUT-en: notatet logges som endring, og endringen
        er aktivitet."""
        o = self._oppdrag()
        _eldes(o, 4)
        svar = self.klient.put(f'/oppdrag/api/oppdrag/{o.pk}/', data={'fritekst': 'Ny tekst'},
                               content_type='application/json')
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertEqual(self._detalj(o)['fritekst'], 'Ny tekst')

    def test_statistikkens_annet_sted_liste_foelger_fristen(self):
        from oppdrag.statistikk import oppdrag_stats
        o = self._oppdrag()
        tekster = lambda: [a['tekst'] for a in oppdrag_stats(self.vakt)['avreist_til']['annet_tekster']]  # noqa: E731
        self.assertEqual(tekster(), [STED])
        _eldes(o, 4)
        self.assertEqual(tekster(), [])


class FeiingenTests(FristBasis):

    def test_purge_old_logs_toemmer_bare_det_utloepte_og_raden_staar(self):
        gammel = self._oppdrag()
        fersk = self._oppdrag()
        _eldes(gammel, 4)
        call_command('purge_old_logs', stdout=StringIO())
        gammel.refresh_from_db()
        fersk.refresh_from_db()
        self.assertEqual(gammel.fritekst, '')
        self.assertFalse(Statusmelding.objects.filter(oppdrag=gammel).exclude(sted_tekst='').exists())
        self.assertEqual(gammel.problemstilling, 'Udefinert', 'raden står — statistikken trenger den')
        self.assertEqual(fersk.fritekst, NOTAT)
        self.assertTrue(Statusmelding.objects.filter(oppdrag=fersk, sted_tekst=STED).exists())

    def test_toerrkjoeringen_teller_og_roerer_ingenting(self):
        o = self._oppdrag()
        _eldes(o, 4)
        ut = StringIO()
        call_command('purge_old_logs', '--dry-run', stdout=ut)
        o.refresh_from_db()
        self.assertEqual(o.fritekst, NOTAT)
        self.assertEqual(fritekstfrist.antall_utlopte(timezone.now()), 1)

    def test_feiingen_starter_ikke_klokka_paa_nytt_og_er_idempotent(self):
        """`update()`, ikke `save()`: ellers ville feiingen selv vært aktivitet."""
        o = self._oppdrag()
        _eldes(o, 4)
        foer = fritekstfrist.frist_for(Oppdrag.objects.get(pk=o.pk))[0]
        self.assertEqual(fritekstfrist.tom_utlopte(timezone.now()), 1)
        self.assertEqual(fritekstfrist.frist_for(Oppdrag.objects.get(pk=o.pk))[0], foer)
        self.assertEqual(fritekstfrist.tom_utlopte(timezone.now()), 0)

    def test_feiingen_melder_endringen_til_sentralbordet(self):
        from core import endringer
        from oppdrag.endringer import OPPDRAG
        o = self._oppdrag()
        _eldes(o, 4)
        foer = endringer.versjon(OPPDRAG)
        with self.captureOnCommitCallbacks(execute=True):
            fritekstfrist.tom_utlopte(timezone.now())
        self.assertNotEqual(endringer.versjon(OPPDRAG), foer)

    def test_oppdrag_uten_tekst_telles_ikke(self):
        o = self._oppdrag(fritekst='', sted_tekst='')
        _eldes(o, 4)
        self.assertEqual(fritekstfrist.tom_utlopte(timezone.now()), 0)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class InnstillingenTests(TestCase):

    def test_handleren_validerer_og_lagrer(self):
        from django.core.exceptions import ValidationError

        from oppdrag.portalinnstillinger import OppdragInnstillinger
        h = OppdragInnstillinger()
        self.assertEqual(h.valider({}), {}, 'fraværende felt er «behold»')
        for ugyldig in ('', '0', '31', 'tre'):
            with self.subTest(ugyldig=ugyldig), self.assertRaises(ValidationError):
                h.valider({'oppdrag_fritekst_dager': ugyldig})
        h.lagre(h.valider({'oppdrag_fritekst_dager': '5'}))
        self.assertEqual(fritekstfrist.frist_dager(), 5)

    def test_feltet_staar_paa_siden(self):
        admin = CustomUser.objects.create_user(
            username='adm_frist', password='x', role='admin', must_change_password=False)
        klient = Client()
        klient.force_login(admin)
        svar = klient.get('/portal-admin/innstillinger/')
        self.assertContains(svar, 'name="oppdrag_fritekst_dager"')
        self.assertContains(svar, 'value="3"')


class NedtellingenTests(SimpleTestCase):
    """`notatSlettesTekst()` i node, og gjennom `renderHistorikk()` — den ekte
    raden — så kallstedet ikke kan forsvinne uten at noe blir rødt."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
        (OPPDRAG_SENTRAL_JS, ('notatSlettesTekst', 'notatSlettesHtml', 'renderHistorikk',
                              'oppdragsnr', 'hastegradKlasse')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def _kjor(self, kode):
        ut = run_node(build_harness(self.HARNESS), kode)
        return [json.loads(linje) for linje in ut.splitlines() if linje != 'OK']

    def test_teksten(self):
        (ut,) = self._kjor("""
            const naa = Date.parse('2026-10-10T12:00:00Z');
            const om = (min) => new Date(naa + min * 60000).toISOString();
            console.log(JSON.stringify([
              notatSlettesTekst(om(30), naa), notatSlettesTekst(om(5 * 60 + 10), naa),
              notatSlettesTekst(om(3 * 24 * 60), naa), notatSlettesTekst(om(2 * 24 * 60 + 4 * 60), naa),
              notatSlettesTekst(om(0), naa), notatSlettesTekst(om(-10), naa),
              notatSlettesTekst(null, naa), notatSlettesTekst('tull', naa)]));
        """)
        self.assertEqual(ut, ['Notatet slettes om under en time', 'Notatet slettes om 5 t',
                              'Notatet slettes om 3 d', 'Notatet slettes om 2 d 4 t',
                              '', '', '', ''])

    def test_historikkraden_viser_nedtellingen_bare_med_tekst(self):
        (ut,) = self._kjor("""
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: (id) => (id === 'historikkliste' ? el : null) };
            globalThis.OPPDRAG_TILGANG = { erAdmin: false };
            const om = new Date(Date.now() + 26 * 3600 * 1000).toISOString();
            const rad = (fritekst, slettes) => ({ id: 1, nummer: 7, hastegrad: 'Haster',
              problemstilling: 'Fall', enheter: [], enhet_navn: 'Bil', lokasjon_navn: 'Scene',
              historikk_fra: '2026-10-10T12:00:00Z', avbrutt_av: [], fritekst, fritekst_slettes: slettes });
            globalThis.historikkliste = [rad('<b>Kari</b>', om)];
            renderHistorikk();
            const med = el.innerHTML;
            globalThis.historikkliste = [rad('', null)];
            renderHistorikk();
            console.log(JSON.stringify([med.includes('Notatet slettes om 1 d'),
                                        med.includes('<b>Kari</b>'),
                                        el.innerHTML.includes('slettes')]));
        """)
        self.assertEqual(ut, [True, False, False])
