"""`/portal-admin/vakt/` — alt om vakta på ett sted (28. sep. 2026).

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

**Alt er global admin** (`admin_required`), som resten av `/portal-admin/`. Arbeidet
gjøres av `core/vaktslutt.py`; denne fila kjenner ingen modul ved navn.
"""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core import vaktslutt
from core.auth_decorators import admin_required
from core.models import AppSetting, Vakt
from core.ratelimit import rate_limit
from core.vakt import VaktnavnOpptatt, hent_aktiv_vakt, vaktnavn_opptatt_melding


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


@admin_required
@require_GET
def vakt_view(request):
    from core.vaktstatistikk import tidligere_vakter

    vakt = hent_aktiv_vakt()
    oppforinger = tidligere_vakter()
    # Nedtrekket i statistikken velges med `?vakt=<nøkkel>`: den nyeste
    # oppføringen for hver vakt, og hvert arkiv uten vakt for seg.
    statistikk_for_vakt = {}
    for oppforing in oppforinger:
        if oppforing.get('vakt_id'):
            statistikk_for_vakt.setdefault(oppforing['vakt_id'], oppforing['nokkel'])
    arkiver = _arkiver()
    for rad in arkiver:
        if rad['vakt_id']:
            rad['nokkel'] = statistikk_for_vakt.get(rad['vakt_id'])

    kollapset = _kollapsede_vakter()
    tidligere = [
        {'vakt': v, 'kan_gjenaapnes': v.pk not in kollapset,
         'nokkel': statistikk_for_vakt.get(v.pk)}
        for v in Vakt.objects.filter(er_aktiv=False).order_by('-avsluttet', '-startet')
    ]
    return render(request, 'core/vakt.html', {
        'vakt': vakt,
        'oversikt': vaktslutt.oversikt(vakt),
        'tidligere': tidligere,
        'arkiver': arkiver,
    })


@admin_required
@require_POST
@rate_limit(group='portaladmin:vakt-navn', rate='20/m', method='POST', on_limit='html')
def vakt_navn_view(request):
    """Gi den aktive vakta nytt navn. Samme regler som ved start: påkrevd og unikt
    — to vakter med samme navn lar seg ikke skille i statistikken."""
    vakt = hent_aktiv_vakt()
    navn = (request.POST.get('navn') or '').strip()
    if not navn:
        messages.error(request, 'Vakta må ha et navn.')
    elif Vakt.objects.filter(navn=navn).exclude(pk=vakt.pk).exists():
        messages.error(request, vaktnavn_opptatt_melding(navn))
    else:
        vakt.navn = navn
        vakt.save(update_fields=['navn'])
        messages.success(request, f'Vakta heter nå «{navn}».')
    return redirect('portaladmin:vakt')


@admin_required
@require_POST
@rate_limit(group='portaladmin:vakt-avslutt', rate='5/m', method='POST', on_limit='html')
def vakt_avslutt_view(request):
    """Avslutt den aktive vakta og start en ny (`core/vaktslutt.py`).

    Krever avkrysningen `bekreft` i tillegg til `data-confirm` i nettleseren: den
    første er en port serveren håndhever, den andre bare et spørsmål.
    """
    if request.POST.get('bekreft') != 'ja':
        messages.error(request, 'Kryss av for at du har sett oversikten.')
        return redirect('portaladmin:vakt')
    nytt_navn = (request.POST.get('ny_vakt_navn') or '').strip()
    if not nytt_navn:
        messages.error(request, 'Den nye vakta må ha et navn — det settes ved vaktstart.')
        return redirect('portaladmin:vakt')
    # Tidlig, så et åpenbart opptatt navn ikke koster en backup. Vernet er
    # `opprett_vakt` i orkestratoren — denne sjekken er et kappløp.
    if Vakt.objects.filter(navn=nytt_navn).exists():
        messages.error(request, vaktnavn_opptatt_melding(nytt_navn))
        return redirect('portaladmin:vakt')

    vakt = hent_aktiv_vakt()
    try:
        svar = vaktslutt.avslutt(vakt, ny_vakt_navn=nytt_navn, bruker=request.user,
                                 request=request)
    except vaktslutt.Sperret as sperret:
        for grunn in sperret.grunner:
            messages.error(request, grunn)
        return redirect('portaladmin:vakt')
    except VaktnavnOpptatt as feil:
        messages.error(request, str(feil))
        return redirect('portaladmin:vakt')

    deler = []
    for h in vaktslutt.all_handlers():
        n = svar['tomt'].get(h.slug, 0)
        deler.append(f'{n} {h.entall if n == 1 and h.entall else h.etikett}')
    messages.success(request, (
        f'Arkivert og tømt: {", ".join(deler) or "ingenting"}. Statistikken er frosset. '
        f'«{svar["avsluttet_vakt"]}» er avsluttet, og «{svar["ny_vakt"]}» er aktiv.'))
    return redirect('portaladmin:vakt')


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
                                f'ikke lenger, og vakta kan ikke gjenåpnes.')
        return redirect('portaladmin:vakt')

    forrige = hent_aktiv_vakt()
    with transaction.atomic():
        if forrige.pk != vakt.pk:
            forrige.er_aktiv = False
            forrige.avsluttet = timezone.now()
            forrige.save(update_fields=['er_aktiv', 'avsluttet'])
        vakt.er_aktiv = True
        vakt.avsluttet = None
        vakt.save(update_fields=['er_aktiv', 'avsluttet'])
        AppSetting.set('aktiv_vakt_id', vakt.pk)
    messages.success(request, f'Vakta «{vakt.navn}» er aktiv igjen.')
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
            messages.error(request, 'Skriv vaktas navn nøyaktig for å slette den.')
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
        'aktiv': vakt.pk == hent_aktiv_vakt().pk or vakt.er_aktiv,
        'oversikt': vaktsletting.oversikt(vakt),
    })


@admin_required
@require_POST
@rate_limit(group='portaladmin:vakt-arkiv-slett', rate='20/m', method='POST', on_limit='html')
def vakt_arkiv_slett_view(request, slug, pk):
    """Slett ett arkiv — samme handling som modulenes egne sletteknapper."""
    from core import vaktsletting

    if request.POST.get('bekreft') != 'ja':
        messages.error(request, 'Bekreftelse mangler.')
        return redirect('portaladmin:vakt')
    try:
        tittel = vaktsletting.slett_arkiv(slug, pk, request=request)
    except (LookupError, ObjectDoesNotExist):
        raise Http404
    messages.success(request, f'Arkivet «{tittel}» er slettet.')
    return redirect('portaladmin:vakt')
