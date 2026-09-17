"""KO-ført ressursstatus — verdimengden, og hvorfor den er kode.

**Dette er ikke oppdragsstatusene.** `oppdrag/choices.py` beskriver en enhets
forløp *på et oppdrag* — venter, rykker ut, fremme, avreist. Et lag uten
oppdrag er ikke «venter»; det står på post. De to verdimengdene svarer på hvert
sitt spørsmål, og å gjenbruke den ene ville tvunget operatøren til å lyve om
den andre.

**Den er kode og ikke en tabell**, i motsetning til `Ressursgruppe`,
`Lokasjon` og problemstillingene. Regelen står i `oppdrag/choices.py` sin egen
docstring og gjelder her: *faglige verdimengder i kode, arrangementsdata i
databasen.* «Ledig», «Opptatt» og «Ute av drift» er språket operatøren og tavla
deler — det skifter ikke med arrangementet, slik en dronegruppe eller et
scenenavn gjør. En tabell her ville dessuten gjort fargene og sorteringen på
tavla til data, og da kan ingen si hva en gul rad betyr.

**Lista er kort med vilje.** Tavla leses i et blikk under sambandstrafikk.
Hver verdi som legges til er en verdi operatøren må velge mellom hver gang, og
et valg til koster mer enn presisjonen det gir — nøyaktig samme avveining som
inkluderingslista i `ko/systemlinjer.py`.
"""
from __future__ import annotations

#: Står på post og kan sendes.
LEDIG = 'ledig'

#: Har noe på gang. **Hva** det er, står i loggen — ikke i statusen: et lag som
#: er opptatt med en pasient og et som rydder etter en konsert er samme sak for
#: den som leter etter noen å sende.
OPPTATT = 'opptatt'

#: Pause, mat, hvil. Skilt fra «Ute av drift» fordi svaret er ulikt: pause kan
#: brytes når det haster, ute av drift kan det ikke.
PAUSE = 'pause'

#: Ikke operativ — mangler folk, utstyr eller er skadet. Kan ikke sendes.
UTE_AV_DRIFT = 'ute_av_drift'

STATUS_VALG: tuple[tuple[str, str], ...] = (
    (LEDIG, 'Ledig'),
    (OPPTATT, 'Opptatt'),
    (PAUSE, 'Pause'),
    (UTE_AV_DRIFT, 'Ute av drift'),
)

STATUS_NAVN: dict[str, str] = dict(STATUS_VALG)

#: Statusen en ressurs har når KO ikke har ført noe. **Utledet, ikke lagret** —
#: samme grunn som `oppdrag.services.enhet_status`: ved vaktstart har ingen
#: ressurs en rad, og «Ledig» er hva fraværet av en føring ser ut som. En
#: lagret standard måtte settes for hver ressurs i hver vaktliste, og da er
#: spørsmålet «hvem glemte å sette den» i stedet for «hvem er ledig».
STANDARD = LEDIG


def er_gyldig(verdi: str) -> bool:
    """Ukjent verdi er **False**, ikke True.

    Samme regel som ukjent nivånavn i tilgangsstigen: en skrivefeil i et
    endepunkt skal stenge døra, ikke åpne den.
    """
    return verdi in STATUS_NAVN
