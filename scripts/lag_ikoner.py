"""Rendrer PNG-ikonene fra `static/img/logo.svg`.

    python scripts/lag_ikoner.py

Krever Playwright med Chromium (utviklerverktøy, ikke i requirements).
SVG-en er kilden; PNG-ene sjekkes inn fordi manifestet trenger dem og prod
ikke har en nettleser å rendre med.

**Bare `<svg>`-taggens bredde og høyde skaleres.** Første utgave byttet ut
`width="512" height="512"` overalt i fila — også på bakgrunnsrektangelet, som
da dekket 180 av 512 enheter i viewBox-en: en blå flekk øverst til venstre
og gjennomsiktig resten (André, 12. sep. 2026: «Den mørke blå bakgrunnen er
delvis vekke»). `core/tests_manifest.py` leser hjørnepikslene og stopper det.
"""
import re
import sys
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
IMG = ROT / 'static' / 'img'

# (fil, størrelse, avrundede hjørner med gjennomsiktig bakgrunn?)
IKONER = [
    ('logo-192.png', 192, True),
    ('logo-512.png', 512, True),
    ('logo-maskable-512.png', 512, False),   # maskable: flaten fyller hele kvadratet
    ('apple-touch-icon.png', 180, False),    # iOS runder selv, og vil ha full flate
]


def svg_for(px: int, avrundet: bool) -> str:
    svg = (IMG / 'logo.svg').read_text(encoding='utf-8')
    if not avrundet:
        # Full flate: hjørneradiusen bort, ellers blir hjørnene gjennomsiktige
        # og iOS/Android legger sin egen (hvite eller svarte) bak.
        svg = svg.replace(' rx="112"', '')
    # Kun rot-elementet skaleres — viewBox-en gjør resten.
    return re.sub(r'(<svg\b[^>]*?)\swidth="512" height="512"',
                  rf'\1 width="{px}" height="{px}"', svg, count=1)


def main() -> int:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        for navn, px, avrundet in IKONER:
            pg = b.new_page(viewport={'width': px, 'height': px}, device_scale_factor=1)
            pg.set_content('<html><body style="margin:0;background:transparent">'
                           + svg_for(px, avrundet) + '</body></html>')
            pg.screenshot(path=str(IMG / navn), omit_background=avrundet,
                          clip={'x': 0, 'y': 0, 'width': px, 'height': px})
            pg.close()
            print('rendret', navn)
        b.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
