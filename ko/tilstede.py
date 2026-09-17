"""Hvem har KO oppe — sidebarens datakilde (`docs/FORSLAG_KO.md` §5.3).

**Den svarer på «hvem har KO oppe», ikke på «hvem dekker samband nå».**
Pålogget er ikke til stede; det står i `CLAUDE.md` og er grunnen til at
`inaktiv_s` er med som kolonne. Skal det siste bli et behov, er det en egen
liten ting og ikke en tolkning av denne lista.

**Notatet sier «`_list_active_sessions` filtrert på `ModulTilgang('ko')`», og
det filteret er feil.** Global admin har ingen `ModulTilgang`-rader og har
likevel tilgang til alt — en rå tabellspørring ville utelatt nettopp den som
sitter i KO og administrerer portalen. Spørsmålet er «har denne kontoen
lesetilgang til `ko`», og svaret er `har_tilgang`-semantikken:

    global admin  →  ja, alltid, uten rader
    andre         →  ja hvis modulen er på **og** kontoen har en rad

Det regnes ut i mengder og ikke per bruker: `har_tilgang()` cacher på
brukerobjektet, så et kall per pålogget konto er to spørringer per konto på en
liste som polles gjennom hele vakta.
"""
from __future__ import annotations

from accounts.models import ModulTilgang
from core.models import ModuleSettings
from core.modules import get_module
from core.sesjoner import aktive_sesjoner

#: Modulens egen slug, ett sted. Brukes av filteret under og av testene.
SLUG = 'ko'


def _har_ko_tilgang_ider(bruker_ider):
    """Delmengden av `bruker_ider` som har lesetilgang til `ko`.

    Speiler `core.auth_decorators.nivaa_for` for én slug, i mengdeform.
    Bevisst *ikke* et kall per bruker: se modulens docstring.
    """
    ider = set(bruker_ider)
    if not ider:
        return set()

    modul = get_module(SLUG)
    if modul is not None and not modul.is_core:
        if SLUG not in ModuleSettings.get_enabled_slugs():
            # Modulen er slått av. Da er det bare global admin igjen — samme
            # svar som `_modul_er_aktiv` gir, og grunnen er den samme: man
            # skal ikke kunne deaktivere seg selv ut av å kunne reaktivere.
            return set()

    return set(
        ModulTilgang.objects
        .filter(modul_slug=SLUG, bruker_id__in=ider)
        .values_list('bruker_id', flat=True)
    )


def _laveste(a, b):
    """Den ferskeste av to `inaktiv_s`-verdier, der `None` er «vet ikke».

    En kjent verdi vinner alltid over `None`: har én av fanene meldt inn
    aktivitet, vet vi noe om personen, og det er det svaret lista skal gi.
    """
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def tilstede():
    """Påloggede kontoer med KO-tilgang, sortert på brukernavn.

    **Én rad per person, ikke per sesjon.** Adminlista på server-status er en
    liste over *sesjoner* — den skal kunne avslutte én av dem. Sidebaren svarer
    på hvem som er der, og den samme operatøren med KO på PC-en og på telefonen
    er én person. Radene slås derfor sammen, og `inaktiv_s` blir den ferskeste
    av fanene: står den ene urørt i to timer mens den andre brukes, er
    personen til stede.

    Radene bærer **ikke** `session_key`. Det er adminflatens håndtak for å
    avslutte en sesjon, og en KO-operatør har ingenting med det å gjøre — se
    `core/sesjoner.py`.

    `er_delt_konto` er med fordi **en delt konto må se ut som en delt konto**
    (§4.5): «Enhet 2» og «Kari Nordmann» betyr fundamentalt ulike ting — den
    ene er en person, den andre er to til tre man må slå opp i vaktlista for å
    finne. §5.2 vil etter hvert sperre delte kontoer ute av alt annet enn
    `oppdrag`, men den sperren finnes ikke ennå, og til den gjør det skal lista
    si sant om det den viser.
    """
    fra_sesjoner = aktive_sesjoner()
    admin_ider = {b.id for b, _ in fra_sesjoner
                  if getattr(b, 'role', None) == 'admin'}
    med_rad = _har_ko_tilgang_ider(
        {b.id for b, _ in fra_sesjoner if b.id not in admin_ider})
    slipper_inn = admin_ider | med_rad

    per_bruker = {}
    for bruker, rad in fra_sesjoner:
        if bruker.id not in slipper_inn:
            continue
        forrige = per_bruker.get(bruker.id)
        if forrige is None:
            per_bruker[bruker.id] = {
                'brukernavn': bruker.username,
                'er_delt_konto': bool(getattr(bruker, 'er_delt_konto', False)),
                'er_global_admin': bruker.id in admin_ider,
                'inaktiv_s': rad['inaktiv_s'],
            }
        else:
            forrige['inaktiv_s'] = _laveste(forrige['inaktiv_s'], rad['inaktiv_s'])

    rader = list(per_bruker.values())
    rader.sort(key=lambda r: r['brukernavn'].lower())
    return rader
