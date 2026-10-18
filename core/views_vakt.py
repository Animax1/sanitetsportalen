"""`/admin/vakt/` — alt om vakta på ett sted (28. sep. 2026).

André: «Innstillinger er spesifikke funksjoner. /vakt er overordnet for denne
vakten.» Fram til nå lå vakta på tre steder: navnet i portalinnstillingene,
avslutning og gjenåpning under pasientenes innstillinger — fordi pasient-
registreringen var den eneste modulen da vakta ble innført — og tidligere
vakter i statistikken. Knappen som avslutter *hele* portalen sto gjemt i én
modul; «Hvordan avslutter jeg vakten nå da?» var spørsmålet som flyttet den.

**Serverrendret, uten egen JS-fil.** Oversikten og sperrene regnes ut når siden
lastes, skjemaene poster og videresender (PRG), og bekreftelsen er
`data-confirm` fra `ui-actions.js`, som backupsiden. Malen escaper selv, så det
finnes ingen mal-strenger å skanne.

**Admin og moderator** (fase 5c, 17. okt. 2026, `docs/BESLUTNING_PORTALER.md` §4.8):
navn og «Avslutt vakt» har to innganger — `/admin/vakt/` og `/moderator/vakt/` — og én
kropp hver. Avslutningen er reversibel (`pre_reset`-backup, gjenåpning), og uten den
ville admin vært flaskehals for hver kamp. **Gjenåpning, sletting og arkivene står hos
admin**: de er enten irreversible, eller går på tvers av portalene. Moderatorens side
viser dem ikke, og rutene er `admin_required`.

Arbeidet gjøres av `core/vaktslutt.py`; denne fila kjenner ingen modul ved navn.
"""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core import vaktslutt
from core.auth_decorators import admin_required, moderator_kreves
from core.models import Vakt
from core.ratelimit import rate_limit
from core.vakt import (
    VaktnavnOpptatt, gjor_aktiv, hent_aktiv_vakt, laas_aktiv_vakt, vaktnavn_opptatt_melding,
)


def _kollapsede_vakter() -> set[int]:
    """Vakter der et arkiv er kollapset: radnivået finnes ikke, og en «aktiv»
    vakt uten rådata ville løyet. Gjennom arkivregisteret — før sjekket
    pasientmodulen bare sitt eget arkiv, og en kollapset oppdragsvakt kunne
    gjenåpnes."""
    from core.arkiv import all_handlers

    ider = set()
    for handler in all_handlers():
        modell = getattr(handler, 'arkiv_model', None)
        if modell is not None:
            ider.update(modell.objects.filter(kollapset_at__isnull=False, vakt__isnull=False)
                        .values_list('vakt_id', flat=True))
    return ider


def _arkiver() -> list[dict]:
    """Arkivene fra alle modulene, nyeste først. Lesevisning: se, og gå til
    tallene. Radene, signaturen og slettingen står fortsatt i modulen."""
    from core.arkiv import all_handlers
    from core.modules import get_module

    rader = []
    for handler in all_handlers():
        modell = getattr(handler, 'arkiv_model', None)
        if modell is None:
            continue
        modul = get_module(handler.slug)
        for arkiv in modell.objects.select_related('vakt'):
            rader.append({
                'modul': modul.name if modul else handler.slug,
                'slug': handler.slug,
                'pk': arkiv.pk,
                'tittel': arkiv.tittel,
                'vakt_id': arkiv.vakt_id,
                'vakt': arkiv.vakt.navn if arkiv.vakt_id else '',
                'importert_at': arkiv.importert_at,
                # To navn på samme ting: `VaktArkiv` er eldre enn `AbstractArkiv`
                # og kan ikke bytte felt uten å bryte signaturene (rot-CLAUDE.md).
                'antall': getattr(arkiv, 'antall_rader', getattr(arkiv, 'antall_pasienter', None)),
                'kollapset_at': arkiv.kollapset_at,
                # Arkiv uten vakt er sin egen oppføring i statistikkens nedtrekk
                # (`tidligere_vakter`); de andre får vaktas nøkkel i viewet.
                'nokkel': None if arkiv.vakt_id else f'arkiv:{handler.slug}:{arkiv.pk}',
            })
    return sorted(rader, key=lambda r: r['importert_at'], reverse=True)


def _tilbake(request):
    """Siden innsendingen kom fra: moderatorens eller admins."""
    return 'core:moderator_vakt' if request.path.startswith('/moderator/') else 'portaladmin:vakt'


def _side(request, *, admin: bool):
    from core.vaktstatistikk import tidligere_vakter

    vakt = hent_aktiv_vakt()
    oppforinger = tidligere_vakter()
    # Nedtrekket i statistikken velges med `?vakt=<nøkkel>`: den nyeste
    # oppføringen for hver vakt, og hvert arkiv uten vakt for seg.
    statistikk_for_vakt = {}
    for oppforing in oppforinger:
        if oppforing.get('vakt_id'):
            statistikk_for_vakt.setdefault(oppforing['vakt_id'], oppforing['nokkel'])
    # Arkivene går på tvers av portalene, og slettingen er admins.
    arkiver = _arkiver() if admin else []
    for rad in arkiver:
        if rad['vakt_id']:
            rad['nokkel'] = statistikk_for_vakt.get(rad['vakt_id'])

    kollapset = _kollapsede_vakter()
    # Alle i portalen utenom den aktive. For admin også en vakt uten portal
    # (lastet fra en backup tatt før portalene fantes), så den kan gjenåpnes
    # og tas inn — ellers ville den forsvunnet fra lista uten spor.
    hvilke = Q(portal=vakt.portal) | Q(portal__isnull=True) if admin else Q(portal=vakt.portal)
    tidligere = [
        {'vakt': v, 'kan_gjenaapnes': v.pk not in kollapset,
         'nokkel': statistikk_for_vakt.get(v.pk)}
        for v in (Vakt.objects.filter(hvilke)
                  .exclude(pk=vakt.pk).order_by('-avsluttet', '-startet'))
    ]
    navnerom = 'portaladmin' if admin else 'core'
    return render(request, 'core/vakt.html', {
        'vakt': vakt,
        'oversikt': vaktslutt.oversikt(vakt),
        'tidligere': tidligere,
        'arkiver': arkiver,
        'admin': admin,
        'url_navn': reverse(f'{navnerom}:{"vakt_navn" if admin else "moderator_vakt_navn"}'),
        'url_avslutt': reverse(f'{navnerom}:{"vakt_avslutt" if admin else "moderator_vakt_avslutt"}'),
    })


def _navn(request):
    """Gi den aktive vakta nytt navn. Samme regler som ved start: påkrevd og unikt
    — to vakter med samme navn lar seg ikke skille i statistikken."""
    vakt = hent_aktiv_vakt()
    navn = (request.POST.get('navn') or '').strip()
    if not navn:
        messages.error(request, 'Vakten må ha et navn.')
    elif Vakt.objects.filter(portal=vakt.portal, navn=navn).exclude(pk=vakt.pk).exists():
        messages.error(request, vaktnavn_opptatt_melding(navn))
    else:
        vakt.navn = navn
        vakt.save(update_fields=['navn'])
        messages.success(request, f'Vakten heter nå «{navn}».')
    return redirect(_tilbake(request))


def _avslutt(request):
    """Avslutt den aktive vakta og start en ny (`core/vaktslutt.py`).

    Krever avkrysningen `bekreft` i tillegg til `data-confirm` i nettleseren: den
    første er en port serveren håndhever, den andre bare et spørsmål. Vakta er
    den aktive **i portalen forespørselen står i** — en moderator når ingen annen.
    """
    tilbake = _tilbake(request)
    if request.POST.get('bekreft') != 'ja':
        messages.error(request, 'Kryss av for at du har sett oversikten.')
        return redirect(tilbake)
    nytt_navn = (request.POST.get('ny_vakt_navn') or '').strip()
    if not nytt_navn:
        messages.error(request, 'Den nye vakten må ha et navn — det settes ved vaktstart.')
        return redirect(tilbake)
    # Tidlig, så et åpenbart opptatt navn ikke koster en backup. Vernet er
    # `opprett_vakt` i orkestratoren — denne sjekken er et kappløp.
    vakt = hent_aktiv_vakt()
    if Vakt.objects.filter(portal=vakt.portal, navn=nytt_navn).exists():
        messages.error(request, vaktnavn_opptatt_melding(nytt_navn))
        return redirect(tilbake)

    try:
        svar = vaktslutt.avslutt(vakt, ny_vakt_navn=nytt_navn, bruker=request.user,
                                 request=request)
    except vaktslutt.Sperret as sperret:
        for grunn in sperret.grunner:
            messages.error(request, grunn)
        return redirect(tilbake)
    except VaktnavnOpptatt as feil:
        messages.error(request, str(feil))
        return redirect(tilbake)

    deler = []
    for h in vaktslutt.all_handlers():
        n = svar['tomt'].get(h.slug, 0)
        deler.append(f'{n} {h.entall if n == 1 and h.entall else h.etikett}')
    messages.success(request, (
        f'Arkivert og tømt: {", ".join(deler) or "ingenting"}. Statistikken er frosset. '
        f'«{svar["avsluttet_vakt"]}» er avsluttet, og «{svar["ny_vakt"]}» er aktiv.'))
    return redirect(tilbake)


@admin_required
@require_GET
def vakt_view(request):
    return _side(request, admin=True)


@admin_required
@require_POST
@rate_limit(group='portaladmin:vakt-navn', rate='20/m', method='POST', on_limit='html')
def vakt_navn_view(request):
    return _navn(request)


@admin_required
@require_POST
@rate_limit(group='portaladmin:vakt-avslutt', rate='5/m', method='POST', on_limit='html')
def vakt_avslutt_view(request):
    return _avslutt(request)


@moderator_kreves
@require_GET
def moderator_vakt_view(request):
    return _side(request, admin=False)


@moderator_kreves
@require_POST
@rate_limit(group='moderator:vakt-navn', rate='20/m', method='POST', on_limit='html')
def moderator_vakt_navn_view(request):
    return _navn(request)


@moderator_kreves
@require_POST
@rate_limit(group='moderator:vakt-avslutt', rate='5/m', method='POST', on_limit='html')
def moderator_vakt_avslutt_view(request):
    return _avslutt(request)


@admin_required
@require_POST
@rate_limit(group='portaladmin:vakt-gjenaapne', rate='10/m', method='POST', on_limit='html')
def vakt_gjenaapne_view(request, pk):
    """Gjenåpne en avsluttet vakt.

    En feilklikk-avslutning skal ikke være en katastrofe uten vei tilbake (§7.2).
    Gjenåpningen bytter aktiv vakt; den henter **ikke** arkiverte rader tilbake —
    de ligger i arkivene og i `pre_reset`-backupene. De frosne tallene står;
    avsluttes vakta igjen, fryses et sett til ved siden av.

    Døra er låst når et arkiv for vakta er kollapset: da finnes ikke radnivået.
    """
    vakt = get_object_or_404(Vakt, pk=pk)
    if vakt.pk in _kollapsede_vakter():
        messages.error(request, f'Et arkiv for «{vakt.navn}» er kollapset — radnivået finnes '
                                f'ikke lenger, og vakten kan ikke gjenåpnes.')
        return redirect('portaladmin:vakt')

    with transaction.atomic():
        # Låst, og alle andre med flagget ryddes — ikke bare den forrige
        # (28. sep. 2026). Et kappløp kunne etterlate to aktive; dette retter
        # opp også en slik tilstand, i stedet for å bygge videre på den.
        laas_aktiv_vakt(vakt.portal)
        # Under låsen: en sletting kan ha holdt den, og vakta er borte når vi
        # slipper til (tredje gjennomgang 29. sep. — ellers 500).
        if not Vakt.objects.filter(pk=vakt.pk).exists():
            messages.error(request, f'«{vakt.navn}» ble slettet før den rakk å gjenåpnes.')
            return redirect('portaladmin:vakt')
        # Slår av den andre aktive i samme portal før denne slås på (17. okt. 2026).
        gjor_aktiv(vakt)
    messages.success(request, f'Vakten «{vakt.navn}» er aktiv igjen.')
    return redirect('portaladmin:vakt')


# ── Sletting (28. sep. 2026) ─────────────────────────────────────────────────
#
# André: «jeg vil ha en slett knapp. Noen er test vakter som kan og skal
# slettes.» Arbeidet gjøres av `core/vaktsletting.py`.

@admin_required
@require_http_methods(['GET', 'POST'])
@rate_limit(group='portaladmin:vakt-slett', rate='5/m', method='POST', on_limit='html')
def vakt_slett_view(request, pk):
    """Slett en tidligere vakt med alt som hører til.

    **GET viser hva som forsvinner** — pasienter, oppdrag, KO-logg,
    lagregistreringer, vaktlister, arkiver og frosne tall — og POST krever at
    vaktas navn skrives inn. Et avkrysningsfelt blir klikket bort; et navn må
    leses. Det er den irreversible handlingen på siden, og porten er deretter.
    """
    from core import vaktsletting

    vakt = get_object_or_404(Vakt, pk=pk)
    if request.method == 'POST':
        if (request.POST.get('navn') or '').strip() != vakt.navn:
            messages.error(request, 'Skriv vaktens navn nøyaktig for å slette den.')
            return redirect('portaladmin:vakt_slett', pk=vakt.pk)
        try:
            slettet = vaktsletting.slett_vakt(vakt, bruker=request.user, request=request)
        except vaktsletting.KanIkkeSlettes as feil:
            messages.error(request, str(feil))
            return redirect('portaladmin:vakt')
        deler = ', '.join(f'{etikett}: {n}' for etikett, n in slettet) or 'ingen rader'
        messages.success(request, f'«{vakt.navn}» er slettet ({deler}). En hel backup ble tatt først.')
        return redirect('portaladmin:vakt')

    return render(request, 'core/vakt_slett.html', {
        'vakt': vakt,
        'aktiv': vakt.er_aktiv,
        'oversikt': vaktsletting.oversikt(vakt),
    })


@admin_required
@require_http_methods(['GET', 'POST'])
@rate_limit(group='portaladmin:vakt-arkiv-slett', rate='20/m', method='POST', on_limit='html')
def vakt_arkiv_slett_view(request, slug, pk):
    """Slett ett arkiv — samme tjeneste som modulenes egne sletteknapper.

    **Samme port som vaktslettingen** (sikkerhetsgjennomgangen 28. sep. 2026):
    GET viser arkivet, og POST krever at tittelen skrives inn. Før var
    bekreftelsen et skjult `bekreft=ja` og en nettleserdialog — én rød lenke per
    rad i en lang liste, for noe som kan være det eneste som står igjen av en
    vakt. Backupen tas av tjenesten, `core.vaktsletting.slett_arkiv`.
    """
    from core import vaktsletting

    try:
        handler, arkiv = vaktsletting.finn_arkiv(slug, pk)
    except (LookupError, ObjectDoesNotExist):
        raise Http404
    if request.method == 'POST':
        if (request.POST.get('tittel') or '').strip() != arkiv.tittel:
            messages.error(request, 'Skriv arkivets tittel nøyaktig for å slette det.')
            return redirect('portaladmin:vakt_arkiv_slett', slug=slug, pk=pk)
        try:
            tittel = vaktsletting.slett_arkiv(slug, pk, bruker=request.user, request=request)
        except vaktsletting.KanIkkeSlettes as feil:
            messages.error(request, str(feil))
            return redirect('portaladmin:vakt')
        except ObjectDoesNotExist:
            raise Http404
        messages.success(request, f'Arkivet «{tittel}» er slettet. En backup ble tatt først.')
        return redirect('portaladmin:vakt')

    from core.modules import get_module
    modul = get_module(handler.slug)
    return render(request, 'core/vakt_arkiv_slett.html', {
        'arkiv': arkiv, 'slug': slug,
        'modul': modul.name if modul else handler.slug,
        # Samme to navn som i `_arkiver()`.
        'antall': getattr(arkiv, 'antall_rader', getattr(arkiv, 'antall_pasienter', None)),
        'kollapset': bool(arkiv.kollapset_at),
    })
