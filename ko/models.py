"""KO-modulen har ingen egne modeller ennå (pulje 1).

Skallet eier ingen data. Ressursbildet er en **projeksjon** av `vaktliste` og
`oppdrag` og skal aldri bli et register her — se `docs/FORSLAG_KO.md` §3.1 og
§9.1: bilene ville da finnes to steder, og feilen oppstår ikke ved opprettelse
men ved endring, når noen retter kallesignalet ett sted og tavla og
enhetsskjermen viser ulike navn på samme bil midt i en vakt.

Det som *skal* bli modeller her, kommer med sine puljer: logglinja (pulje 2) og
`Hendelse` (pulje 3). Fila finnes fordi Django forventer den, og fordi fraværet
ellers leses som at noen glemte den.
"""
