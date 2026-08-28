"""Modul-deklarasjon for oppdrag-appen.

Oppdragshåndtering for bil og beredskapsambulanse. Se
``docs/BESLUTNING_OPPDRAGSMODULEN.md``.

**Skjult i meny og dashboard inntil fase 3.** Modulen er registrert allerede
nå slik at admin kan tildele tilgang i matrisen og forberede kontoer, men den
har ingen side ennå. Et modulkort som fører til 404 er nettopp «en knapp som
fører til en vegg» — og den er verre enn ingen knapp.

Når sentralbordet og enhetsskjermen finnes (fase 3 og 4), settes ``url`` og de
to ``show_*``-flaggene. `OppdragModulSynlighetTests` feiler hvis flaggene slås
på uten at URL-en finnes, slik at de to ikke kan komme i utakt.
"""
from core.modules import Module


OppdragModule = Module(
    slug='oppdrag',
    name='Oppdrag',
    description=(
        'Oppdragshåndtering for bil og beredskapsambulanse: tildeling, '
        'statusmeldinger og tidsstempler.'
    ),
    url=None,
    icon='truck-front',
    admin_only=False,
    is_core=False,
    order=120,
    show_in_nav=False,
    show_in_dashboard=False,
)
