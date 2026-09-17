"""Rekkefølgen modulfilene må gjenopprettes i, og hva som binder den.

**Hvorfor dette er en modul og ikke bare en liste i en test.** Rekkefølgen sto
skrevet ut for hånd i fire dokumenter og én test. Da KO fikk backup 17. sep.
2026 ble tre av de fire stående uten `ko` — og den ene som var oppdatert var
ikke runbooken, altså nettopp den man følger mens man gjenoppretter. Ingenting
ble rødt, fordi `core/tallfasit.py` teller handlere og ikke leser rekkefølgen.
Samme argument som der: utregningen må ligge et sted den som skal rette et
dokument kan spørre.

**Og den skrevne begrunnelsen var for smal.** Alle fire dokumentene ga én grunn
— «alt peker på vakta med et heltall» — mens `vaktliste.Ressurs.enhet` peker på
`oppdrag.Enhet`, også med et heltall. Den som stokket om på den oppgitte
grunnen ville lagt `vaktliste` rett etter `portal`, og det er lovlig etter
teksten og feiler i praksis:

    IntegrityError: vaktliste_ressurs.enhet_id contains a value '1' that does
    not have a corresponding value in oppdrag_enhet.id

`bindinger()` utleder derfor kantene fra modellene i stedet for å gjenta en
påstand, og `avvik()` sier fra når den skrevne rekkefølgen ikke holder dem.
Det er forskjellen på en rekkefølge som er riktig og en som er *kontrollert*
riktig — og den forskjellen viser seg først den dagen noen gjenoppretter.

**`portal` står ikke i lista fordi den er bundet, men fordi den binder.** Den
bærer `core.Vakt`, som ingen natural key har og derfor lagres som et heltall.
"""
from __future__ import annotations


#: Rekkefølgen modulfilene tas i, i en tom base. `full` står utenfor — den
#: er selvbærende og lastes alene.
GJENOPPRETTINGSREKKEFOLGE: tuple[str, ...] = (
    'portal', 'patients', 'arkiv', 'oppdrag', 'oppdrag_arkiv', 'vaktliste',
    'ko',
)

#: Modulfiler uten en eneste peker ut av sitt eget datasett. De kan tas når
#: som helst, og står utenfor rekkefølgen for å si nettopp det.
#:
#: Lista er ikke en unntaksliste man kan skrive seg inn i: `avvik()` krever at
#: en slug her *faktisk* er uten bindinger. Får `backlog` en peker til vakta i
#: morgen, blir den rød til den flyttes inn i rekkefølgen.
UTEN_BINDING: tuple[str, ...] = ('backlog',)


def som_pilsetning() -> str:
    """`'portal → patients → …'` — formen dokumentene skriver rekkefølgen i."""
    return ' → '.join(GJENOPPRETTINGSREKKEFOLGE)


def _eiere() -> dict[str, str]:
    """{'patients.Patient': 'patients'} — hvilken modulfil hver modell ligger i."""
    from core.backup import all_handlers

    ut: dict[str, str] = {}
    for h in all_handlers():
        if h.slug == 'full':
            continue
        for etikett in h.get_restore_models():
            ut.setdefault(etikett, h.slug)
    return ut


def bindinger() -> dict[str, set[str]]:
    """{slug: {slug den må komme etter}}, utledet fra modellene.

    En kant finnes når en modell i modulens dump har en konkret peker til en
    modell som ligger i en **annen** modulfil, og pekeren ikke er strippet.

    **`OneToOneField` teller med, og det er ikke en detalj.** Et filter på
    `many_to_one` alene går forbi `vaktliste.Vaktliste.vakt` — som er nettopp
    den pekeren dokumentene begrunner rekkefølgen med. Utledningen ville da
    meldt `vaktliste` fri mens den er bundet.

    Pekere ut av portalen i det hele tatt — typisk til `accounts.CustomUser` —
    er ikke en rekkefølge­binding mellom modulfiler og teller ikke her. De
    håndteres av `strip_fields`; se `BrukerpekereStrippesEllerBegrunnesTests`.
    """
    from django.apps import apps as django_apps

    from core.backup import all_handlers

    eiere = _eiere()
    ut: dict[str, set[str]] = {}
    for h in all_handlers():
        if h.slug == 'full':
            continue
        strippet = h.get_strip_fields()
        egne = set(h.get_restore_models())
        krav: set[str] = set()
        for etikett in h.get_restore_models():
            felt_uten = set(strippet.get(etikett.lower(), []))
            for f in django_apps.get_model(etikett)._meta.get_fields():
                if not (f.is_relation and getattr(f, 'concrete', False)):
                    continue
                if not (getattr(f, 'many_to_one', False)
                        or getattr(f, 'one_to_one', False)):
                    continue
                mal = f.related_model._meta.label
                if mal in egne or f.name in felt_uten:
                    continue
                eier = eiere.get(mal)
                if eier is not None and eier != h.slug:
                    krav.add(eier)
        ut[h.slug] = krav
    return ut


def avvik() -> list[str]:
    """Tom liste når den skrevne rekkefølgen holder det modellene krever."""
    from core.backup import all_handlers

    krav = bindinger()
    plassert = list(GJENOPPRETTINGSREKKEFOLGE)
    feil: list[str] = []

    registrerte = {h.slug for h in all_handlers() if h.slug != 'full'}
    kjente = set(plassert) | set(UTEN_BINDING)
    for slug in sorted(registrerte - kjente):
        feil.append(
            f'{slug}: registrert som modulfil, men står verken i '
            f'GJENOPPRETTINGSREKKEFOLGE eller UTEN_BINDING — hvor i '
            f'gjenopprettingen hører den hjemme?')
    for slug in sorted(kjente - registrerte):
        feil.append(f'{slug}: står i rekkefølgen, men ingen handler er '
                    f'registrert med den slugen')
    for slug in sorted(set(plassert) & set(UTEN_BINDING)):
        feil.append(f'{slug}: står begge steder — den er enten bundet eller fri')

    for slug in UTEN_BINDING:
        if krav.get(slug):
            feil.append(
                f'{slug}: står som fri, men peker på '
                f'{", ".join(sorted(krav[slug]))} — flytt den inn i '
                f'rekkefølgen, etter det den peker på')

    for i, slug in enumerate(plassert):
        for maal in sorted(krav.get(slug, set())):
            if maal not in plassert:
                feil.append(f'{slug} peker på {maal}, som ikke er i rekkefølgen')
            elif plassert.index(maal) >= i:
                feil.append(
                    f'{slug} står før {maal}, men peker på den — '
                    f'gjenopprettingen feiler på fremmednøkkelen')
    return feil
