"""Backup-handler for KO-modulen (pulje 2).

**Registrert i samme pulje som modulen fikk sin første tabell**, og det er en
regel og ikke en tilfeldighet: vaktlistemodulen sto uten backup i det hele tatt
fra den gikk i prod til 13. sep. 2026, og det ble oppdaget ved en gjennomgang
og ikke av noe rødt. For KO-loggen er innsatsen høyere enn for de fleste — den
er i praksis dokumentet man leser etter et arrangement der noe gikk galt.

**Dette er en backup, ikke et arkiv, og forskjellen er hele grunnen til at
loggen ser ut som den gjør** (André, 17. sep. 2026). Et arkiv fryser radene med
en SHA-signatur, og et felt i signaturen er låst i 24 måneder ved konstruksjon:
sletteinngangen i §4.4 ville da fått arkivet til å melde tukling. Loggen får
derfor lesbar historikk og ingen signatur. `core/tests_arkiv*` kjenner ingen
`ko`-handler, og det skal den ikke.

**Konsekvensen skal stå skrevet, ikke oppdages senere:** en linje som fjernes
med sletteinngangen ligger fortsatt i denne fila offsite i inntil 730 dager, og
i den hele fila i 90. Det er ikke en sletterett — nøyaktig samme forbehold som
`NOTAT_DPIA_OG_FRITEKST.md` §6 tar for `Oppdrag.fritekst`. Fristen på den
levende raden er ekte beskyttelse mot «noen leser loggen tre måneder senere»,
og den er ikke mer enn det. Står i `PERSONVERN_DOKUMENTASJON.md` A.9.

**Rekkefølgen ved gjenoppretting: portalfila først.** `Logglinje.vakt` peker på
`core.Vakt`, som ingen natural key har og derfor lagres som et heltall. Er
vakta ikke der, feiler hele gjenopprettingen på fremmednøkkelen — samme grunn
som for `patients`, `oppdrag` og `vaktliste`.
"""
from __future__ import annotations

from core.backup import BaseBackupHandler, register


class KoBackupHandler(BaseBackupHandler):
    """Backup av KO-loggen.

    Én enhet, ikke to: modulen har ingen arkivmodell å skille ut, og skal
    ikke få en. Se modulens docstring.
    """

    slug = 'ko'
    display_name = 'KO-logg'

    apps = ['ko']
    exclude = []

    #: FK-er ut av modulens eget datasett.
    #:
    #: Serialiseringen kjører med `natural_foreign`, så en FK til en bruker
    #: lagres som brukernavnet — og er kontoen slettet i mellomtiden, feiler
    #: **hele** gjenopprettingen, altså akkurat når man trenger backupen.
    #:
    #: **Ingen av de tre bærer noe som går tapt.** `forfatter_navn`,
    #: `forfatter_delt_konto` og `fjernet_av_navn` er frosset på raden nettopp
    #: fordi kontoen kan forsvinne (§4.5) — det er de feltene loggen leses med.
    #: FK-ene er bekvemmelighet; de frosne feltene er fasit.
    #:
    #: `Logglinje.vakt` strippes **ikke**: den er en heltallspeker uten
    #: natural key, og den bærer selve tilhørigheten. Prisen er at portalfila
    #: må gjenopprettes først.
    #:
    #: `korrigerer` og `rot` strippes heller ikke — de peker innad i settet, og
    #: uten dem ville en rettet linje kommet tilbake som to linjer som begge
    #: gjelder.
    strip_fields = {
        'ko.Logglinje': ['forfatter', 'fjernet_av'],
    }


def register_handlers() -> None:
    """Kalles fra `KoConfig.ready()`."""
    register(KoBackupHandler())
