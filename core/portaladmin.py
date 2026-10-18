"""Portalene, slik global admin setter dem opp (fase 5a, 17. okt. 2026).

`docs/BESLUTNING_PORTALER.md` §4.1–§4.3. Reglene står her, ikke i viewet,
så de kan prøves uten en side — og så en kommando eller en senere flate
går gjennom de samme sperrene.

| Regel | Hvorfor |
|---|---|
| **Sluggen settes én gang** | Den står i fanevakten (`X-Portal`) og i meldingene til kartet (fase 6). En slug som endres, gjør åpne faner og kartets grupper foreldreløse |
| **Siste aktive portal kan ikke deaktiveres** | Da har ingen en portal å stå i, og alle andre enn admin møter «Ingen portal» |
| **En modul ut av portalen sletter ikke tilgangene** | `ModulTilgang` står, men gir ingenting (`_tilganger`); settes modulen inn igjen, er tilgangene der. Å slette dem ville gjort et feilklikk irreversibelt |
| **Taket må være et nivå modulen har** | Et tak modulen ikke kjenner, ville stengt alt eller ingenting uten at noen så hvorfor |
| **Moderator utnevnes bare av admin** | §4.2: moderator kan aldri gjøre noen til moderator |
"""
from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from core.auth_decorators import NIVAA_HIERARKI
from core.models import Portalmodul, Tilhorighet, Vaktportal

#: Sluggen står i en header og i en URL hos kartet: små bokstaver, tall og
#: bindestrek, som Djangos `slugify` gir — uten æøå, som den gjør om.
SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def foreslaa_slug(navn: str) -> str:
    """«Landsskytterstevnet 2026» → «landsskytterstevnet-2026». Æ, ø og å skrives
    om før `slugify`, som ellers ville strøket dem («r-ros» for «Røros»)."""
    ren = (navn or '').lower().replace('æ', 'ae').replace('ø', 'o').replace('å', 'a')
    return slugify(ren)[:64]


def opprett_portal(navn: str, slug: str = '') -> Vaktportal:
    """Ny portal, med alle modulene og taket på toppen (`core.signals`)."""
    navn = (navn or '').strip()
    if not navn:
        raise ValidationError('Portalen må ha et navn.')
    slug = (slug or '').strip() or foreslaa_slug(navn)
    if not SLUG.match(slug):
        raise ValidationError('Kortnavnet kan bare ha små bokstaver, tall og bindestrek.')
    if Vaktportal.objects.filter(navn__iexact=navn).exists():
        raise ValidationError(f'«{navn}» finnes allerede.')
    if Vaktportal.objects.filter(slug=slug).exists():
        raise ValidationError(f'Kortnavnet «{slug}» er tatt.')
    return Vaktportal.objects.create(navn=navn, slug=slug)


def sett_grunnlag(portal: Vaktportal, *, navn: str, er_aktiv: bool) -> None:
    navn = (navn or '').strip()
    if not navn:
        raise ValidationError('Portalen må ha et navn.')
    if Vaktportal.objects.filter(navn__iexact=navn).exclude(pk=portal.pk).exists():
        raise ValidationError(f'«{navn}» finnes allerede.')
    with transaction.atomic():
        if portal.er_aktiv and not er_aktiv:
            andre = (Vaktportal.objects.select_for_update()
                     .filter(er_aktiv=True).exclude(pk=portal.pk))
            if not andre.exists():
                raise ValidationError(
                    'Dette er den eneste aktive portalen. Uten den har ingen en portal å '
                    'stå i — opprett eller aktiver en annen først.')
        portal.navn = navn
        portal.er_aktiv = er_aktiv
        portal.save(update_fields=['navn', 'er_aktiv'])


def sett_tilhorigheter(portal: Vaktportal, ider) -> None:
    """Portalens utvalg fra katalogen (§4.3) — styrer både moderatorens
    brukerliste og vaktlistas korps. Ukjente ID-er avvises."""
    ider = {int(i) for i in ider}
    rader = list(Tilhorighet.objects.filter(pk__in=ider))
    if len(rader) != len(ider):
        raise ValidationError('Listen inneholder ukjente tilhørigheter — last siden på nytt.')
    portal.tilhorigheter.set(rader)


def sett_moduler(portal: Vaktportal, onsket: dict) -> list[tuple]:
    """`{slug: tak | None}` for hver registrert modul. `None` tar modulen ut.

    Returnerer endringene `[(slug, fra, til)]`. Alt valideres før noe skrives.
    """
    from core.modules import get_all_modules

    # Modulene bare admin når (`core`, `accounts`) står utenfor: de gates av
    # global admin, og et tak betyr ingenting for dem.
    moduler = {m.slug: m for m in get_all_modules() if not m.admin_only}
    ukjente = set(onsket) - set(moduler)
    if ukjente:
        raise ValidationError(f'Ukjent modul: {", ".join(sorted(ukjente))}.')
    for slug, tak in onsket.items():
        if tak is not None and (tak not in moduler[slug].nivaaer or tak not in NIVAA_HIERARKI):
            raise ValidationError(
                f'«{moduler[slug].name}» har ikke nivået «{tak}» — velg et av modulens.')
    naa = dict(Portalmodul.objects.filter(portal=portal).values_list('modul_slug', 'tak'))
    endringer = [(slug, naa.get(slug), tak) for slug, tak in onsket.items()
                 if naa.get(slug) != tak]
    with transaction.atomic():
        for slug, _fra, til in endringer:
            if til is None:
                # `delete()` per rad, ikke på spørringen: auditen er et signal.
                for rad in Portalmodul.objects.filter(portal=portal, modul_slug=slug):
                    rad.delete()
            else:
                rad, ny = Portalmodul.objects.get_or_create(
                    portal=portal, modul_slug=slug, defaults={'tak': til})
                if not ny:
                    rad.tak = til
                    rad.save(update_fields=['tak'])
    return endringer


def sett_moderator(portal: Vaktportal, bruker, er_moderator: bool) -> None:
    """Gjør kontoen til moderator i portalen, eller til vanlig medlem igjen.

    En moderator er alltid medlem — raden opprettes om den mangler. Å ta bort
    rollen fjerner ikke medlemskapet: det er moderatorens egen jobb (fase 5b).
    """
    from accounts.models import PortalRolle, Portaltilgang

    if getattr(bruker, 'role', None) == 'admin':
        raise ValidationError('Global admin styrer alle portaler, og trenger ikke rollen.')
    if er_moderator:
        tilgang, _ = Portaltilgang.objects.get_or_create(bruker=bruker, portal=portal)
        if tilgang.rolle != PortalRolle.MODERATOR:
            tilgang.rolle = PortalRolle.MODERATOR
            tilgang.save(update_fields=['rolle'])
    else:
        # `save()` per rad, ikke `update()`: endringen skal gjennom signalene.
        for tilgang in Portaltilgang.objects.filter(bruker=bruker, portal=portal,
                                                    rolle=PortalRolle.MODERATOR):
            tilgang.rolle = PortalRolle.MEDLEM
            tilgang.save(update_fields=['rolle'])


# ── Tilhørighetene (18. okt. 2026) ───────────────────────────────────────────
#
# André: «korpsene bør settes opp av admin UTENFOR /vaktliste — det blir dårlig
# design å sette opp hvem korpser de får når de er inni en annen modul.» Katalogen
# er felles for alle portaler (beslutning 10), og bare admin endrer den.

def bruk_av(tilhorighet) -> int:
    """Hvor mange rader som peker på tilhørigheten — kontoer, mannskap, ressurser,
    skift. **Utledet av modellene**, ikke en liste: `core` kjenner ingen modul ved
    navn, og en ny peker skal telle uten at noen husker å legge den til her.
    Portalenes utvalg (M2M) er ikke bruk — det er katalogens plass i portalen."""
    antall = 0
    for rel in tilhorighet._meta.related_objects:
        if rel.one_to_many:
            antall += getattr(tilhorighet, rel.get_accessor_name()).count()
    return antall


def _rens(navn, kortnavn, type_):
    navn = (navn or '').strip()
    if not navn:
        raise ValidationError('Tilhørigheten må ha et navn.')
    if type_ not in dict(Tilhorighet.TYPE_VALG):
        raise ValidationError('Velg korps eller annet.')
    return navn, (kortnavn or '').strip()[:20]


def opprett_tilhorighet(navn, kortnavn='', type_=Tilhorighet.KORPS, portaler=()) -> Tilhorighet:
    """Ny i katalogen, og med i de valgte portalene."""
    navn, kortnavn = _rens(navn, kortnavn, type_)
    if Tilhorighet.objects.filter(navn__iexact=navn).exists():
        raise ValidationError(f'«{navn}» finnes allerede.')
    with transaction.atomic():
        t = Tilhorighet.objects.create(navn=navn, kortnavn=kortnavn, type=type_)
        for portal in portaler:
            portal.tilhorigheter.add(t)
    return t


def endre_tilhorighet(t, *, navn, kortnavn, type_, er_aktiv) -> None:
    navn, kortnavn = _rens(navn, kortnavn, type_)
    if Tilhorighet.objects.filter(navn__iexact=navn).exclude(pk=t.pk).exists():
        raise ValidationError(f'«{navn}» finnes allerede.')
    t.navn, t.kortnavn, t.type, t.er_aktiv = navn, kortnavn, type_, er_aktiv
    t.save(update_fields=['navn', 'kortnavn', 'type', 'er_aktiv'])


def slett_tilhorighet(t) -> None:
    """Bare en som ingenting peker på. Ellers: sett den inaktiv — da skjules den i
    nedtrekkene, men står der den alt er brukt."""
    n = bruk_av(t)
    if n:
        raise ValidationError(f'«{t.navn}» er i bruk ({n}) og kan ikke slettes. Sett den inaktiv '
                              'i stedet.')
    t.delete()


def sett_kontoens_tilhorigheter(bruker, ider) -> list[tuple]:
    """Kontoens tilhørigheter fra brukersiden. Returnerer `[(navn, 'ja'|'nei')]`
    for audit. Domenedata, ikke tilgang — samme skille som `Mannskap.user`."""
    from core.models import Kontotilhorighet

    ider = {int(i) for i in ider}
    rader = {t.pk: t for t in Tilhorighet.objects.filter(pk__in=ider)}
    if len(rader) != len(ider):
        raise ValidationError('Listen inneholder ukjente tilhørigheter — last siden på nytt.')
    naa = dict(Kontotilhorighet.objects.filter(bruker=bruker)
               .values_list('tilhorighet_id', 'tilhorighet__navn'))
    endringer = []
    with transaction.atomic():
        for pk in set(naa) - ider:
            # `delete()` per rad: auditsignalene skal fyre der de finnes.
            for rad in Kontotilhorighet.objects.filter(bruker=bruker, tilhorighet_id=pk):
                rad.delete()
            endringer.append((naa[pk], 'nei'))
        for pk in ider - set(naa):
            Kontotilhorighet.objects.create(bruker=bruker, tilhorighet=rader[pk])
            endringer.append((rader[pk].navn, 'ja'))
    return endringer
