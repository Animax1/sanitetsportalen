"""Moderatorens brukere — reglene for `/moderator/brukere/` (fase 5b, 17. okt. 2026).

`docs/BESLUTNING_PORTALER.md` §4.2, §4.3 og §4.11, beslutning 7, 8 og 13. Reglene
står her og ikke i viewet, så de kan prøves uten en side.

| Regel | Hvorfor |
|---|---|
| **Moderatoren ser kontoene med portalens tilhørigheter, og portalens medlemmer** | Beslutning 8. Kontoer utenfor ser hun ikke — ellers er portalgrensen en liste over hele installasjonen |
| **Global admin står utenfor** | Admin har alle portaler uten rader; en moderator som kunne fjerne eller endre en admin, styrte over den som utnevnte henne |
| **En moderator rører ikke en moderator, heller ikke seg selv** | §4.2: moderatorer utnevnes av admin. Kunne de fjerne hverandre, var utnevnelsen en mening og ikke en regel |
| **Fjerning tar medlemskapet, aldri kontoen** | Beslutning 7. Kontoen kan være med i en annen portal; modulradene går med (`CASCADE`) |
| **Aldri over taket, aldri over eget nivå** | §4.2. `utdelbart()` er grensen, og matrisen tilbyr ikke mer |
| **En ny konto er en person, med en av portalens tilhørigheter** | §4.3. Uten tilhørighet forsvinner den fra moderatorens egen liste i det den fjernes fra portalen |
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Q

from core.auth_decorators import NIVAA_HIERARKI, er_global_admin, nivaa_for
from core.models import Kontotilhorighet, Portalmodul
from core.sortering import norsk_nokkel

from .models import CustomUser, PortalRolle, Portaltilgang


def synlige_kontoer(portal):
    """Kontoene moderatoren ser: portalens tilhørigheter, og portalens medlemmer.

    Medlemmene er med selv uten tilhørighet — en bil, eller en konto admin la
    til — ellers kunne moderatoren ikke se, og ikke fjerne, noen som står i
    hennes egen portal.
    """
    return (CustomUser.objects
            .filter(Q(tilhorigheter__tilhorighet__in=portal.tilhorigheter.all())
                    | Q(portaltilganger__portal=portal))
            .exclude(role='admin')
            .distinct())


def grupper(portal):
    """`[(tilhørighet | None, [(konto, rolle | None)])]`, sortert på tilhørighet og navn.

    En konto med to av portalens tilhørigheter står under begge: lista er
    sortert *på* tilhørighet (beslutning 8), og den som leter under HGSD skal
    finne henne der. `None` er medlemmene uten noen av dem.
    """
    kontoer = list(synlige_kontoer(portal))
    roller = dict(Portaltilgang.objects.filter(portal=portal, bruker__in=kontoer)
                  .values_list('bruker_id', 'rolle'))
    tilh = sorted(portal.tilhorigheter.all(), key=lambda t: norsk_nokkel(t.navn))
    par = set(Kontotilhorighet.objects.filter(bruker__in=kontoer, tilhorighet__in=tilh)
              .values_list('bruker_id', 'tilhorighet_id'))

    def _sortert(rader):
        return sorted(((k, roller.get(k.pk)) for k in rader),
                      key=lambda r: norsk_nokkel(r[0].fullt_navn or r[0].username))

    ut = []
    for t in tilh:
        rader = [k for k in kontoer if (k.pk, t.pk) in par]
        if rader:
            ut.append((t, _sortert(rader)))
    med_tilh = {b for b, _ in par}
    uten = [k for k in kontoer if k.pk not in med_tilh]
    if uten:
        ut.append((None, _sortert(uten)))
    return ut


def kan_styre(aktor, portal, bruker) -> None:
    """Kast `ValidationError` hvis `aktor` ikke får endre `bruker` i portalen.

    Hver regel står én gang: global admin er ikke blant de synlige, og en
    moderator som prøver seg selv, treffer moderatorsperra — de var egne `if`-er
    en stund, og mutasjonene viste at ingen av dem avgjorde noe.
    """
    if not synlige_kontoer(portal).filter(pk=bruker.pk).exists():
        raise ValidationError('Kontoen hører ikke til portalen, eller styres bare av admin.')
    if er_global_admin(aktor):
        return
    if Portaltilgang.objects.filter(bruker=bruker, portal=portal,
                                    rolle=PortalRolle.MODERATOR).exists():
        raise ValidationError('En moderator — også du selv — endres bare av en administrator.')


def legg_til(aktor, portal, bruker) -> bool:
    """Gjør kontoen til medlem. `True` hvis den ikke var det fra før."""
    kan_styre(aktor, portal, bruker)
    _, ny = Portaltilgang.objects.get_or_create(bruker=bruker, portal=portal)
    return ny


def fjern(aktor, portal, bruker) -> bool:
    """Ta kontoen ut av portalen, med modulradene. Kontoen står. `True` hvis den var med."""
    kan_styre(aktor, portal, bruker)
    fjernet = False
    # `delete()` per rad, ikke på spørringen: audit- og cachesignalene skal fyre.
    for tilgang in Portaltilgang.objects.filter(bruker=bruker, portal=portal):
        tilgang.delete()
        fjernet = True
    return fjernet


def utdelbart(aktor, portal) -> dict:
    """`{modul_slug: høyeste nivå aktor kan dele ut}` i portalen.

    Det laveste av portalens tak og aktors eget nivå. Global admin får taket.
    En modul aktor ikke har, er ikke med — der deler hun ingenting ut.
    """
    tak = dict(Portalmodul.objects.filter(portal=portal).values_list('modul_slug', 'tak'))
    if er_global_admin(aktor):
        return {s: t for s, t in tak.items() if t in NIVAA_HIERARKI}
    ut = {}
    for slug, taket in tak.items():
        eget = nivaa_for(aktor, slug, portal=portal)
        # Et ukjent tak gir allerede `None` her — `_i_portalen` stenger det.
        if eget not in NIVAA_HIERARKI:
            continue
        ut[slug] = min(eget, taket, key=NIVAA_HIERARKI.get)
    return ut


def kandidater_til_moderator(portal):
    """Kontoene admin kan gjøre til moderator, sortert på navn: de moderatoren selv
    ville sett (`synlige_kontoer`), utenom dem som alt er moderator.

    `[{'konto', 'tilhorighet' (første av portalens, eller ''), 'medlem'}]`. En
    liste å velge fra, ikke et brukernavn å skrive (18. okt. 2026).
    """
    ut = {}
    for tilh, rader in grupper(portal):
        for konto, rolle in rader:
            if rolle == PortalRolle.MODERATOR:
                continue
            rad = ut.setdefault(konto.pk, {'konto': konto, 'tilhorighet': '', 'medlem': bool(rolle)})
            if tilh is not None and not rad['tilhorighet']:
                rad['tilhorighet'] = tilh.navn
    return sorted(ut.values(),
                  key=lambda r: norsk_nokkel(r['konto'].fullt_navn or r['konto'].username))
