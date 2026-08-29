"""Modul-deklarasjon for oppdrag-appen.

Oppdragshåndtering for bil og beredskapsambulanse. Se
``docs/BESLUTNING_OPPDRAGSMODULEN.md``.

Modulen sto med ``url=None`` og begge ``show_*``-flagg av gjennom fase 1 og 2,
fordi et modulkort som fører til 404 er «en knapp som fører til en vegg». Fra
fase 3 finnes sentralbordet, og flaggene er slått på.

``/oppdrag/`` serverer **to grensesnitt**: sentralbordet, og enhetsskjermen for
kontoer som er knyttet til en ``Enhet``. Valget tas av koblingen, ikke av
tilgangsnivået — se ``views_common.er_enhetskonto``.
"""
from core.modules import Module


OppdragModule = Module(
    slug='oppdrag',
    name='Oppdrag',
    description=(
        'Oppdragshåndtering for bil og beredskapsambulanse: tildeling, '
        'statusmeldinger og tidsstempler.'
    ),
    url='/oppdrag/',
    icon='truck-front',
    admin_only=False,
    is_core=False,
    order=120,
    show_in_nav=True,
    show_in_dashboard=True,
)
