"""Modul-deklarasjon for KO-modulen.

KO er **situasjonsverktøyet**: hva skjer på arrangementet, hvem er hvor, hva
vet vi. `/oppdrag/` er enhetsverktøyet — én bil, én statusmaskin, én stempling
om gangen, og ressursen selv sitter med skjermen. Her sitter noen andre enn
ressursen og fører. Se `docs/FORSLAG_KO.md` §1 og `ko/CLAUDE.md`.

**Tre nivåer fra pulje 2, og hvert av dem ble lagt til i den commiten det
begynte å bety noe.** Pulje 1 deklarerte bare `les`, fordi skallet ikke hadde
et eneste skriveendepunkt — et nivå som ikke gir noe er lett å dele ut i god
tro, og ville så **trådt stille i kraft** den dagen loggen landet, uten at noen
tok den avgjørelsen da. Det er nøyaktig feilen den globale nivålista gjorde mot
`statistikk`, dokumentert i `core/modules.py`.

Loggen gir de to neste mening, og de er delt der skaden er ulik:

| Nivå | Kan |
|---|---|
| `les` | Se loggen for **aktiv vakt** |
| `skriv_full` | Føre linjer, og rette sine egne og andres — retting er en ny rad, så ingenting går tapt |
| `skriv_leder` | Sletteinngangen (§4.4), og tidligere vakters logg. Etiketten bærer ordet «leder», som `LedernivaaetsPlassIStigenTests` krever av hver modul som deklarerer trinnet |

**Skillet mot `skriv_full` er hva slags skade en feil gjør**, som i vaktlista:
den som fører kan rette tilbake, fordi en retting er en ny rad som peker på den
gamle. Den som fjerner en linje tømmer innholdet for godt — det er hele
poenget med inngangen — og etter det finnes teksten bare i en backupfil ingen
har en knapp til.

**Historikken er `skriv_leder` av en annen grunn: dataminimering** (André,
17. sep. 2026). En ny operatør på vakt i kveld har ingen operativ grunn til å
lese fjorårets helseopplysninger, og opplæring hører hjemme på en demo-vakt og
ikke på ekte linjer. Selve flata kommer i pulje 3; nivået er skrevet nå fordi
det er nå `les` får sin betydning — «aktiv vakt», ikke «alt».

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
    nivaaer=('les', 'skriv_full', 'skriv_leder'),
    # **Egne etiketter, fordi samme nivå betyr ulike ting** (`CLAUDE.md`).
    # `skriv_full` er «redigerer felter» i pasientmodulen og «fører loggen»
    # her; uten etiketten deles nivået ut i god tro med feil modul i hodet.
    nivaa_navn=(
        ('les', 'Lese: situasjonsbildet og loggen'),
        ('skriv_full', 'Føre loggen og hendelsene: linjer, åpne og lukke hendelser'),
        ('skriv_leder', 'KO-leder: fjerner linjer, leser tidligere vakter'),
    ),
)
