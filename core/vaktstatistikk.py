"""Statistikken for en avsluttet vakt, frosset per fane (28. sep. 2026).

Steg 1 av planen i `TODO.md` («Avslutt vakt, arkiv og tidligere vakter i
statistikken»). Når en vakt avsluttes, regnes hver fane i `core/stats.py` ut
**før** radene tømmes, og tallene lagres i `core.VaktStatistikk`. Etter det
leser statistikken for den vakta de frosne tallene, ikke radene.

**Hvorfor her og ikke i hver modul:** registeret finnes allerede. En modul som
melder inn en statistikkhandler, får tallene sine frosset uten å gjøre noe mer
— på samme måte som en backuphandler får en backup. Statistikkappen kjenner
ingen kildemodul ved navn, og dette gjør det heller ikke.

**Alt eller ingenting.** Feiler én fane, kaster `frys()`, og kalleren — som
står i samme transaksjon som slettingen — ruller alt tilbake. Å avslutte en
vakt med halve statistikken borte er verre enn å ikke få avsluttet den.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.models import VaktStatistikk
from core.stats import all_handlers


def frys(vakt, *, bruker=None) -> list[VaktStatistikk]:
    """Regn ut og lagre hver fane for `vakt`. Returnerer radene, én per fane.

    **Kalles før radene tømmes**, i samme transaksjon. Alle radene i ett sett
    får samme `frosset_at`; det er den som skiller to avslutninger av samme
    vakt (se `VaktStatistikk`).

    Hver registrert handler fryses, også for en modul som er slått av:
    dataene finnes uansett, og om modulen er på er et spørsmål om i dag, ikke
    om vakta. Hvem som får *se* tallene avgjøres ved lesing, som for de
    levende.
    """
    naa = timezone.now()
    navn = getattr(bruker, 'username', '') or ''
    with transaction.atomic():
        return [
            VaktStatistikk.objects.create(
                vakt=vakt, vakt_navn=vakt.navn, slug=handler.slug,
                versjon=handler.statistikk_versjon,
                data=handler.full_stats(vakt),
                frosset_at=naa, frosset_av=bruker, frosset_av_navn=navn,
            )
            for handler in all_handlers()
        ]


def tidligere_vakter() -> list[dict]:
    """Vaktene statistikken kan vise, nyeste først (steg 3).

    Hver oppføring har `kilder`: fanens slug → hvor tallene hentes fra, enten
    `{'type': 'frosset', 'id': <VaktStatistikk>}` eller `{'type': 'arkiv',
    'id': <arkiv>}`.

    **To slags kilder, fordi historien har to:**

    - **Frosne sett** — alt som er avsluttet etter 28. sep. 2026. Én oppføring
      per avslutning; en gjenåpnet vakt har to.
    - **Arkiver** fra før frysingen fantes, for vakter uten frosset sett. Da
      finnes tallene bare der. Et arkiv uten vakt — laget før vaktene fantes,
      som LS2026 i mai 2026 (`patients/0014` fylte ikke pekeren inn) — blir
      en oppføring for seg, med arrangementsnavnet.

    Har en vakt et frosset sett, vises ikke arkivene dens i tillegg: settet er
    tallene slik fanen viste dem, og det samme en gang til er støy.

    Ingen tilgangsfiltrering her — det gjør statistikkappen, som for de
    levende tallene. Arkivene finnes gjennom `core.arkiv`-registeret, så denne
    fila kjenner ingen modul ved navn.
    """
    from core.arkiv import all_handlers as arkivhandlere

    sett: dict[tuple, dict] = {}
    for rad in VaktStatistikk.objects.order_by('-frosset_at', 'slug'):
        oppforing = sett.setdefault((rad.vakt_id, rad.frosset_at), {
            'nokkel': f'frosset:{rad.vakt_id or 0}:{rad.frosset_at.isoformat()}',
            'navn': rad.vakt_navn,
            'tidspunkt': rad.frosset_at.isoformat(),
            'kilder': {},
        })
        oppforing['kilder'][rad.slug] = {'type': 'frosset', 'id': rad.pk}
    frosne_vakter = {vakt_id for vakt_id, _ in sett if vakt_id}

    arkivert: dict[str, dict] = {}
    for handler in arkivhandlere():
        modell = getattr(handler, 'arkiv_model', None)
        if modell is None:
            continue
        # Nyeste først: har en vakt to arkiver i samme modul, vises det siste.
        for arkiv in modell.objects.select_related('vakt').order_by('-importert_at'):
            if arkiv.vakt_id in frosne_vakter:
                continue
            nokkel = (f'vakt:{arkiv.vakt_id}' if arkiv.vakt_id
                      else f'arkiv:{handler.slug}:{arkiv.pk}')
            oppforing = arkivert.setdefault(nokkel, {
                'nokkel': nokkel,
                'navn': (arkiv.vakt.navn if arkiv.vakt_id else
                         getattr(arkiv, 'arrangement_navn', '') or arkiv.tittel),
                'tidspunkt': arkiv.importert_at.isoformat(),
                'kilder': {},
            })
            oppforing['kilder'].setdefault(handler.slug, {'type': 'arkiv', 'id': arkiv.pk})
            oppforing['tidspunkt'] = max(oppforing['tidspunkt'], arkiv.importert_at.isoformat())

    alle = list(sett.values()) + list(arkivert.values())
    return sorted(alle, key=lambda o: o['tidspunkt'], reverse=True)
