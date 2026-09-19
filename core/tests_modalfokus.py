"""Fokus slippes ut av modalen før Bootstrap skjuler den (14. sep. 2026).

**Advarselen André meldte fra staging**, på flere vinduer i `/vaktliste/` og
`/oppdrag/`:

    Blocked aria-hidden on an element because its descendant retained focus.
    Element with focus: <button.btn-close>
    Ancestor with aria-hidden: <div.modal fade#oppdragDetaljModal>

Bootstrap 5.3 setter `aria-hidden="true"` på modalen når den lukkes, men
flytter ikke fokus ut av den først. Lukker du med krysset, blir fokus stående
på `.btn-close` inne i noe som nettopp ble skjult for skjermlesere.

Det er ikke bare konsollstøy: nettleseren *nekter* å sette `aria-hidden` når
det skjer, så modalen blir liggende eksponert for skjermlesere etter at den
visuelt er borte — og brukeren som navigerer med tastatur mister fokuspunktet
sitt i samme øyeblikk.

`slippFokusFoerSkjul()` bor i `portal-utils.js` fordi lytteren skal dekke hver
modal på hver side, og `hide.bs.modal` bobler. Den er navngitt og ikke anonym
av samme grunn som `klikkSkalKjore()`: en `if` inne i en lytter lar seg ikke
kjøre her.
"""
from django.test import SimpleTestCase

from patients.js_test_utils import (
    PORTAL_UTILS_JS, build_harness, node_available, read_js, run_node,
)


class ModalFokusTests(SimpleTestCase):

    HARNESS = ((PORTAL_UTILS_JS, ('slippFokusFoerSkjul',)),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    # Minimalt DOM: en modal som «inneholder» krysset, og et element utenfor.
    FORSPILL = '''
    let blurret = 0;
    const kryss = { navn: 'btn-close', blur: () => { blurret += 1; } };
    const utenfor = { navn: 'utenfor', blur: () => { blurret += 1; } };
    const modal = { navn: 'modal', contains: (el) => el === kryss };
    '''

    def test_fokus_i_modalen_slippes(self):
        run_node(self.harness, self.FORSPILL + """
            assert(slippFokusFoerSkjul(modal, kryss) === true, 'skal ha sluppet fokus');
            assert(blurret === 1, 'blur skal ha blitt kalt en gang');
        """)

    def test_fokus_utenfor_modalen_rores_ikke(self):
        """Lukkes modalen mens fokus står et annet sted på siden — et
        bakgrunnsfelt, en knapp i verktøylinja — skal vi ikke rive fokus
        vekk derfra. Advarselen gjelder bare etterkommere."""
        run_node(self.harness, self.FORSPILL + """
            assert(slippFokusFoerSkjul(modal, utenfor) === false, 'utenfor skal staa');
            assert(blurret === 0, 'blur skal ikke ha blitt kalt');
        """)

    def test_uten_fokus_i_det_hele_tatt(self):
        """`document.activeElement` kan være `null` (og er `<body>` i praksis,
        som ikke ligger i modalen). Lytteren skal ikke kaste da — den fyrer på
        hver eneste modallukking i portalen."""
        run_node(self.harness, self.FORSPILL + """
            assert(slippFokusFoerSkjul(modal, null) === false, 'null skal gi false');
            assert(slippFokusFoerSkjul(null, kryss) === false, 'ingen modal skal gi false');
            assert(blurret === 0, 'ingenting skal ha blitt blurret');
        """)

    def test_element_uten_blur_gir_ikke_typefeil(self):
        """SVG-noder og enkelte innslag har ikke `blur()`. Et kast her ville
        stoppet Bootstraps egen skjuling midt i."""
        run_node(self.harness, self.FORSPILL + """
            const rart = { navn: 'uten-blur' };
            const m = { contains: (el) => el === rart };
            assert(slippFokusFoerSkjul(m, rart) === false, 'skal svare false, ikke kaste');
        """)

    def test_lytteren_er_koblet_paa_hide_bs_modal(self):
        """Funksjonen kan være aldri så riktig — uten koblingen fyrer den ikke.
        `hide`, ikke `hidden`: etter `hidden.bs.modal` er `aria-hidden` alt satt,
        og da er advarselen allerede avgitt."""
        kilde = read_js(PORTAL_UTILS_JS)
        self.assertIn("addEventListener('hide.bs.modal'", kilde)
        # Andre lyttere på `hidden.bs.modal` er lov (nullstillingen av skjemaer,
        # 19. sep. 2026) — men ikke *denne*: fokus må slippes før `aria-hidden`.
        for i in [m.start() for m in re.finditer(r"addEventListener\('hidden\.bs\.modal'", kilde)]:
            self.assertNotIn('slippFokusFoerSkjul', kilde[i:i + 200])
