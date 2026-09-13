"""Backup-handler for vaktlistemodulen (13. sep. 2026).

**Modulen hadde ingen dekning i det hele tatt fram til nå.** Korps, mannskap med
telefon, e-post og ISSI, kompetanser, ressursgrupper og -roller, ressursene,
vaktpostene, vaktlistene og belastningsgrensene lå utenfor alle fire backupfiler
siden appen gikk i prod 11. september. Det er samme feil oppdragsmodulen hadde
fram til sin fase 7, og den er ikke synlig noe sted før dagen man trenger
filene.

Én enhet, ikke to. Vaktlista har ikke noe arkiv som fryser og skal beskyttes mot
en restore av den aktive dataen — `Vaktliste.arkivert` er et flagg på raden, og
raden hører til samme datasett som resten.

**Rekkefølgen ved gjenoppretting i tom base: portalfila først.**
`Vaktliste.vakt` peker på `core.Vakt`, som ingen natural key har og derfor
lagres som et heltall. Er vakta ikke der, feiler hele gjenopprettingen på
fremmednøkkelen. Det samme gjelder `Ressurs.enhet` og oppdragsmodulen.
"""
from __future__ import annotations

from core.backup import BaseBackupHandler, register


class VaktlisteBackupHandler(BaseBackupHandler):
    """Backup av hele vaktlistemodulen.

    Slettelista før `loaddata` utledes av `apps` (barn før foreldre), så en
    modell som legges til senere blir dekket uten at noen må huske en liste.
    """

    slug = 'vaktliste'
    display_name = 'Vaktliste'

    apps = ['vaktliste']
    exclude = []

    #: FK-er ut av modulens eget datasett.
    #:
    #: Serialiseringen kjører med `natural_foreign`, så en FK til en bruker
    #: lagres som brukernavnet. Er kontoen slettet i mellomtiden, feiler
    #: **hele** gjenopprettingen med DeserializationError — altså akkurat når
    #: man trenger backupen. Ingen av de tre er nødvendige for å forstå
    #: dataene:
    #:
    #: - `Mannskap.user` er kontokoblingen, og den er domenedata som settes på
    #:   nytt av lederen (eller av seg selv, via e-postadressen). En vaktliste
    #:   uten koblinger er fullt lesbar; en som ikke lar seg gjenopprette er
    #:   ikke det.
    #: - `Vaktliste.satt_i_drift_av` og `Utsending.sendt_av` er spor, og sporet
    #:   som betyr noe ligger i audit-loggen.
    #:
    #: `Vaktliste.vakt` og `Ressurs.enhet` strippes **ikke**: de er
    #: heltallspekere uten natural key, og de bærer selve tilhørigheten —
    #: hvilken vakt lista gjelder, og hvilken bil ressursen er koblet til.
    #: Prisen er at portalfila og oppdragsfila må gjenopprettes først.
    strip_fields = {
        'vaktliste.Mannskap': ['user'],
        'vaktliste.Vaktliste': ['satt_i_drift_av'],
        'vaktliste.Utsending': ['sendt_av'],
    }


def register_handlers() -> None:
    """Kalles fra `VaktlisteConfig.ready()`."""
    register(VaktlisteBackupHandler())
