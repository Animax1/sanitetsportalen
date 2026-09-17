"""Modul-deklarasjon for KO-modulen.

KO er **situasjonsverktøyet**: hva skjer på arrangementet, hvem er hvor, hva
vet vi. `/oppdrag/` er enhetsverktøyet — én bil, én statusmaskin, én stempling
om gangen, og ressursen selv sitter med skjermen. Her sitter noen andre enn
ressursen og fører. Se `docs/FORSLAG_KO.md` §1 og `ko/CLAUDE.md`.

**Bare `les` er deklarert (pulje 1), og det er et bevisst valg.**
Skallet har ingen skriveendepunkter. Et nivå som ikke gir noe er lett å dele ut
i god tro — det er nøyaktig feilen den globale nivålista gjorde mot
`statistikk`, dokumentert i `core/modules.py`. Her er den verre enn der: et
`skriv_full` delt ut i dag ville ligget i basen og **trådt stille i kraft** den
dagen pulje 2 landet, uten at noen tok den avgjørelsen da. Hver pulje legger
til sitt eget nivå i det øyeblikket nivået betyr noe, og et nytt trinn er
additivt — matrisen tilbyr bare det modulen deklarerer.

**Loggen skal ha samme tilgangsnivå som pasientdata, ikke et lettere** (§4.4).
«Mann, ca. 60, kollapset ved scene sør 21:14» er indirekte identifiserende på
et arrangement med kjent deltakerliste, og det er helseopplysninger uansett.
Det er en regel om hvem som får raden, ikke om hvilke nivåer som finnes, og
den håndheves ved utdeling.
"""
from core.modules import Module


KoModule = Module(
    slug='ko',
    name='KO',
    description=(
        'Situasjonsbildet: ressursoversikt, oppdragsliste, logg og hendelser. '
        'Eier ingen ressurser selv — tavla settes sammen av vaktlista og '
        'oppdragsmodulen.'
    ),
    url='/ko/',
    icon='broadcast-pin',
    admin_only=False,
    is_core=False,
    # Etter oppdrag (120). KO er laget over de andre og leser dem; rekkefølgen
    # i menyen sier det samme som avhengighetsretningen gjør.
    order=125,
    show_in_nav=True,
    show_in_dashboard=True,
    nivaaer=('les',),
    nivaa_navn=(
        ('les', 'Lese: situasjonsbildet'),
    ),
)
