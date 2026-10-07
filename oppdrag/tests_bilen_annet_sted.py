"""Bilens skjerm: «Annet sted»-feltet overlever pollingen (7. okt. 2026).

André: «Når enheter skriver i annet sted i /oppdrag så hopper den ut etter ca
15 sekunder.» `pollOgSynk` hvert 15. sekund kaller `lastMine()`, som tegner
det aktive kortet på nytt med `innerHTML` — og feltet bilen skrev i ble byttet
ut med et tomt. På telefonen lukket tastaturet seg samtidig.

Testene går gjennom den ekte inngangen, `lastMine()` → `renderAlt()` →
`renderAktivt()`, ikke bare regelen: en test som kaller `stedfeltetErApent()`
selv, ville gått grønn om kallstedet i `renderAktivt` forsvant. Og
`data-oppdrag` hentes fra markupen kortet faktisk tegnet, så feltet og regelen
ikke kan gli fra hverandre uten at noe blir rødt.
"""
import json

from django.test import SimpleTestCase

from oppdrag import tests_xss
from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, PORTAL_UTILS_JS, build_harness, node_available, run_node,
)


class AnnetStedOverleverPollingenTests(SimpleTestCase):

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', 'klokke')),
        (OPPDRAG_ENHET_JS, ('lastMine', 'renderAlt', 'renderAktivt', 'stedfeltetErApent',
                            'harNyDelt', 'erNyDelt', 'delteLinjerBlokk',
                            'hendelsesnr', 'oppdragsnr', '_antallRad', '_udefinertVarsel',
                            'tidslinjeEnhetHtml', 'hastegradKlasse', '_stedvalg',
                            '_grovsorteringsrad', '_kanGrovsortere', '_varsledeRad',
                            '_problemMedAntall', '_medAntall')),
    )

    #: Et DOM med to elementer: kortet, og feltet når det står der. Pollingen
    #: svarer 200 med `svar` — ETag-en treffer ikke, som når noe er endret.
    OPPSETT = tests_xss.AvreistTilOgGrovsorteringTests.STUBB + """
        const NY_DELT_MS = 60 * 1000;
        globalThis.stemplingPaagaar = false;
        globalThis.etagMine = null;
        globalThis.renderVentende = () => {}; globalThis.renderAvsluttet = () => {};
        globalThis.visUsendt = () => {};
        globalThis.projiser = (d) => d; globalThis.koLes = () => [];
        globalThis.nyeOppdrag = () => [];
        globalThis.posisjonsdelingTilstand = () => null; globalThis.notePaVakt = () => {};
        const kort = { innerHTML: '' };
        // «Oppdatert hh:mm» settes av `renderAlt` — beviset på at pollingen
        // faktisk kom fram til tegningen. Uten det går «kortet står» grønt
        // også når `lastMine` ga opp før den tegnet noe som helst.
        const stempel = { textContent: '' };
        let felt = null;
        globalThis.document = { getElementById: (id) => ({
          'aktivt-oppdrag': kort, 'stemple-sted-tekst': felt, 'enhet-oppdatert': stempel,
        })[id] || null };
        const oppdrag = (neste) => ({ id: 1, status: 'fremme', status_navn: 'Fremme',
          problemstilling: 'Fallskade', hastegrad: 'Haster', lokasjon_navn: 'Scene',
          opprettet: '2026-10-07T12:00:00Z', fritekst: '', grovsortering: '',
          grovsortering_navn: '', neste_overgang: neste, neste_navn: 'Avreist',
          statusmeldinger: [] });
        let svar = [oppdrag('avreist')];
        globalThis.apiFetch = async () => ({ status: 200, ok: true,
          headers: { get: () => '"ny"' }, json: async () => ({ data: svar }) });

        // Bilen trykker «Avreist» → «Annet sted»: kortet tegnes med feltet, og
        // feltet står i DOM-en med attributtet kortet selv skrev.
        globalThis.mineOppdrag = svar;
        globalThis.velgerStedFor = 1; globalThis.velgerAnnetSted = true;
        renderAlt();
        const m = kort.innerHTML.match(/id="stemple-sted-tekst"[^>]*data-oppdrag="([^"]*)"/);
        assert(m, 'feltet bærer oppdraget det gjelder');
        felt = { dataset: { oppdrag: m[1] }, value: 'Legevakt Kar' };
        const skrevet = kort.innerHTML;
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kjor(self, etter):
        return json.loads(run_node(self.harness, self.OPPSETT + etter).splitlines()[0])

    def test_pollingen_tegner_ikke_over_feltet(self):
        """Feilen André meldte: to pollinger midt i skrivingen, og kortet —
        med feltet og teksten i det — står der det sto."""
        ut = self._kjor("""
            kort.innerHTML = 'SKRIVER'; stempel.textContent = '';
            await lastMine(); await lastMine();
            console.log(JSON.stringify([kort.innerHTML, felt.value, stempel.textContent !== '']));
        """)
        self.assertEqual(ut, ['SKRIVER', 'Legevakt Kar', True])

    def test_oppdraget_gikk_videre_da_tegnes_kortet(self):
        """KO flyttet kjeden mens bilen skrev: et felt for et stempel som ikke
        lenger er neste, skal ikke stå igjen og se gyldig ut."""
        ut = self._kjor("""
            kort.innerHTML = 'SKRIVER';
            svar = [oppdrag('leverer')];
            await lastMine();
            console.log(JSON.stringify([kort.innerHTML === 'SKRIVER']));
        """)
        self.assertEqual(ut, [False])

    def test_oppdraget_er_borte_da_tegnes_kortet(self):
        ut = self._kjor("""
            kort.innerHTML = 'SKRIVER';
            svar = [];
            await lastMine();
            console.log(JSON.stringify([kort.innerHTML]));
        """)
        self.assertIn('Ledig', ut[0])

    def test_et_annet_oppdrag_paa_samme_steg_holder_ikke_feltet(self):
        """KO flyttet bilen til et nytt oppdrag som også venter på «Avreist»:
        feltet gjaldt det gamle, og kortet skal vise det nye. Funnet ved
        mutasjon — uten id-kravet sto feltet igjen over feil oppdrag."""
        ut = self._kjor("""
            kort.innerHTML = 'SKRIVER';
            svar = [{ ...oppdrag('avreist'), id: 2 }];
            await lastMine();
            console.log(JSON.stringify([kort.innerHTML === 'SKRIVER']));
        """)
        self.assertEqual(ut, [False])

    def test_lukket_felt_hindrer_ikke_tegningen(self):
        """«Avbryt» og stempelet lukker feltet; da er kortet vanlig igjen."""
        ut = self._kjor("""
            kort.innerHTML = 'SKRIVER';
            globalThis.velgerAnnetSted = false;
            await lastMine();
            console.log(JSON.stringify([kort.innerHTML === 'SKRIVER']));
        """)
        self.assertEqual(ut, [False])

    def test_et_felt_for_et_annet_oppdrag_teller_ikke(self):
        """Det er feltet i DOM-en som avgjør, ikke tilstanden alene."""
        ut = self._kjor("""
            kort.innerHTML = 'SKRIVER';
            felt = { dataset: { oppdrag: '2' }, value: 'x' };
            await lastMine();
            console.log(JSON.stringify([kort.innerHTML === 'SKRIVER']));
        """)
        self.assertEqual(ut, [False])

    def test_foerste_tegning_viser_feltet(self):
        """Feltet finnes ikke før kortet har tegnet det — sperren må ikke
        stoppe tegningen som åpner det."""
        ut = run_node(self.harness, self.OPPSETT + """
            console.log(JSON.stringify([skrevet.includes('id="stemple-sted-tekst"')]));
        """).splitlines()[0]
        self.assertEqual(json.loads(ut), [True])
