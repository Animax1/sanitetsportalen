"""Vaktlista som fil — reserven når portalen er nede (12. sep. 2026).

Én selvstendig HTML-fil med stilene inni, som åpner uten nett og skrives ut
fra nettleseren. Innholdet er utskriftslista: gruppert på ressursgruppe og
ressurs, skiftene sortert på fra, til, navn, med korps, rolle, telefon og
ISSI. **Ikke** e-post, notat eller merknad — fila havner i innbokser, og
fritekst er der helseopplysninger dukker opp.

Ukryptert, etter vurdering 12. sep. 2026: alminnelige personopplysninger,
fast mottakerliste satt av admin, sendes bare ved «Sett i drift» og på
knapp, hver utsending logges (`Utsending`), og fila sier selv «slett etter
vakta». Se `docs/BESLUTNING_VAKTLISTE.md` §13.

Mottakerne og bryteren for automatisk utsending ligger i `AppSetting`
(`MOTTAKERE_NOKKEL`, `VED_DRIFT_NOKKEL`) og settes under
`/portal-admin/innstillinger/`.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify

from . import overnatting, pauser
from .models import Pause, Ressursgruppe, Utsending, Vaktpost

logger = logging.getLogger(__name__)

MOTTAKERE_NOKKEL = 'vaktliste_fil_mottakere'
VED_DRIFT_NOKKEL = 'vaktliste_fil_ved_drift'
#: Intervallsending mens lista er i drift (André, 13. sep. 2026): «en
#: intervall på sending av epost og checkbox, mail sendes bare hvis det er
#: endringer i vaktlisten». 0 = av.
INTERVALL_NOKKEL = 'vaktliste_fil_intervall_min'
BARE_ENDRET_NOKKEL = 'vaktliste_fil_bare_endret'
MAKS_INTERVALL_MIN = 24 * 60


# ── Innstillingene ───────────────────────────────────────────────────────────

def mottakere() -> list[str]:
    """Adressene admin har satt, én per linje eller kommaseparert."""
    from core.models import AppSetting
    raa = AppSetting.get(MOTTAKERE_NOKKEL, '') or ''
    return [a for a in (x.strip() for x in re.split(r'[,\n;]', raa)) if a]


def sendes_ved_drift() -> bool:
    from core.models import AppSetting
    return AppSetting.get(VED_DRIFT_NOKKEL, '1') == '1'


def intervall_minutter() -> int:
    """Hvor ofte lista sendes på nytt mens den er i drift. 0 = aldri."""
    from core.models import AppSetting
    try:
        return max(0, int(AppSetting.get(INTERVALL_NOKKEL, '0') or 0))
    except (TypeError, ValueError):
        return 0


def bare_ved_endring() -> bool:
    from core.models import AppSetting
    return AppSetting.get(BARE_ENDRET_NOKKEL, '1') == '1'


def valider_mottakere(raa: str) -> list[str]:
    """Adressene i tekstfeltet, eller `ValidationError` med den første som
    ikke ser ut som en adresse."""
    adresser = [a for a in (x.strip() for x in re.split(r'[,\n;]', raa or '')) if a]
    for adresse in adresser:
        try:
            validate_email(adresse)
        except ValidationError:
            raise ValidationError(f'«{adresse}» ser ikke ut som en e-postadresse.')
    return adresser


# ── Fila ─────────────────────────────────────────────────────────────────────

def _kl(t):
    return timezone.localtime(t).strftime('%H:%M') if t else ''


def _dag(t):
    return timezone.localtime(t).strftime('%d.%m') if t else ''


def _tidsspenn(fra, til):
    """«08:00–16:00» innenfor ett døgn, «12.09 20:00 – 13.09 04:00» ellers —
    samme regel som `_tidsspenn()` i vaktliste.js."""
    if not fra or not til:
        return ''
    lf, lt = timezone.localtime(fra), timezone.localtime(til)
    if lf.date() == lt.date():
        return f'{lf:%d.%m} {lf:%H:%M}–{lt:%H:%M}'
    return f'{lf:%d.%m %H:%M} – {lt:%d.%m %H:%M}'


def rader_for(vaktliste):
    """Gruppene med ressursene med skiftene — bare det fila skal bære."""
    poster = (Vaktpost.objects
              .filter(ressurs__vaktliste=vaktliste)
              .select_related('mannskap', 'mannskap__korps', 'rolle', 'ressurs',
                              'ressurs__gruppe', 'korps'))
    per_ressurs: dict[int, list] = {}
    ressurser: dict[int, object] = {}
    for vp in poster:
        ressurser[vp.ressurs_id] = vp.ressurs
        per_ressurs.setdefault(vp.ressurs_id, []).append(vp)

    def _rad(vp):
        if vp.mannskap_id is None:
            korps = 'Åpen for alle' if vp.alle_korps else (
                (vp.korps.kortnavn or vp.korps.navn) if vp.korps_id
                else ((vp.ressurs.korps.kortnavn or vp.ressurs.korps.navn)
                      if vp.ressurs.korps_id else 'Planlagt'))
            return {'ledig': True, 'navn': '— ledig —', 'korps': korps,
                    'rolle': vp.rolle.navn if vp.rolle else '',
                    'tid': _tidsspenn(vp.fra_tid, vp.til_tid),
                    'telefon': '', 'issi': ''}
        m = vp.mannskap
        return {'ledig': False, 'navn': m.navn,
                'korps': m.korps.kortnavn or m.korps.navn,
                'rolle': vp.rolle.navn if vp.rolle else '',
                'tid': _tidsspenn(vp.fra_tid, vp.til_tid),
                'telefon': m.telefon, 'issi': m.issi}

    def _rekkefolge(vp):
        return (vp.fra_tid, vp.til_tid, (vp.mannskap.navn if vp.mannskap_id else '').lower())

    # Pausene (23. sep. 2026): mannskapet ser dem i fila, med mindre admin har
    # skjult dem. Per ressurs, som tekst — fila skal kunne leses uten portalen.
    per_ressurs_pauser: dict[int, list] = {}
    if pauser.vises_for_mannskapet():
        for p in Pause.objects.filter(ressurs__vaktliste=vaktliste).order_by('fra', 'id'):
            per_ressurs_pauser.setdefault(p.ressurs_id, []).append(_tidsspenn(p.fra, p.til))

    grupper = []
    for gruppe in Ressursgruppe.objects.order_by('rekkefolge', 'navn'):
        egne = sorted((r for r in ressurser.values() if r.gruppe_id == gruppe.pk),
                      key=lambda r: (r.rekkefolge, r.navn.lower()))
        deler = []
        for r in egne:
            skift = sorted(per_ressurs[r.pk], key=_rekkefolge)
            deler.append({'navn': r.navn, 'antall': sum(1 for vp in skift if vp.mannskap_id),
                          'ledige': sum(1 for vp in skift if vp.mannskap_id is None),
                          'pauser': per_ressurs_pauser.get(r.pk, []),
                          'skift': [_rad(vp) for vp in skift]})
        if deler:
            grupper.append({'navn': gruppe.navn, 'ressurser': deler})
    return grupper


def antall_skift(grupper) -> int:
    return sum(len(r['skift']) for g in grupper for r in g['ressurser'])


def bygg_fil(vaktliste, naa=None) -> str:
    naa = naa or timezone.now()
    grupper = rader_for(vaktliste)
    vakt = vaktliste.vakt
    return render_to_string('vaktliste/fil.html', {
        'vakt_navn': vakt.navn,
        'spenn': _tidsspenn(vakt.startet, vaktliste.planlagt_slutt) or (
            f'fra {_dag(vakt.startet)} {_kl(vakt.startet)}' if vakt.startet else ''),
        'laget': timezone.localtime(naa).strftime('%d.%m.%Y %H:%M'),
        'grupper': grupper,
        'antall': antall_skift(grupper),
        'i_drift': vaktliste.i_drift,
        # Brannlista (25. sep. 2026): hvem sover hvor, per natt. Står i fila
        # fordi alarmen kan gå når portalen er nede — det er reservens hele
        # poeng.
        'brannliste': overnatting.brannliste(vaktliste),
        'brannrutine': vaktliste.brannrutine,
    })


def filnavn(vaktliste, naa=None) -> str:
    naa = timezone.localtime(naa or timezone.now())
    return f'vaktliste-{slugify(vaktliste.vakt.navn) or "vakt"}-{naa:%Y%m%d-%H%M}.html'


# ── Utsendingen ──────────────────────────────────────────────────────────────

def send_fil(vaktliste, *, bruker=None, utloest=Utsending.KNAPP, adresser=None) -> Utsending:
    """Bygg fila og send den som vedlegg til mottakerne admin har satt.

    Returnerer `Utsending`-raden — med `feil` satt hvis sendingen ikke gikk.
    Kaster aldri: den som ringer (knappen, «Sett i drift») skal kunne melde
    fra uten selv å falle. Uten mottakere sendes ingenting, og raden sier det.
    """
    adresser = list(adresser) if adresser is not None else mottakere()
    naa = timezone.now()
    grupper = rader_for(vaktliste)
    rad = Utsending(
        vaktliste=vaktliste, sendt_av=bruker if getattr(bruker, 'pk', None) else None,
        sendt_av_navn=getattr(bruker, 'username', '') or '',
        utloest=utloest, mottakere=', '.join(adresser), antall_rader=antall_skift(grupper),
        innhold_sha256=signatur(grupper, overnatting.brannliste(vaktliste)))
    if not adresser:
        rad.feil = 'Ingen mottakere er satt under portalinnstillingene.'
        rad.save()
        return rad

    try:
        innhold = bygg_fil(vaktliste, naa)
        melding = EmailMessage(
            subject=f'Vaktliste: {vaktliste.vakt.navn}',
            body=(f'Vedlagt ligger vaktlista for «{vaktliste.vakt.navn}» slik den sto '
                  f'{timezone.localtime(naa):%d.%m.%Y %H:%M}, som reserve hvis portalen er nede.\n\n'
                  f'Fila inneholder navn og telefonnumre. Slett den etter vakta.\n'),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=adresser,
        )
        melding.attach(filnavn(vaktliste, naa), innhold, 'text/html')
        sendt = melding.send(fail_silently=False)
        if not sendt:
            rad.feil = 'E-posttjenesten tok ikke imot meldingen.'
    except Exception as exc:   # noqa: BLE001 — sporet skal ha årsaken
        logger.exception('Vaktlista kunne ikke sendes for vaktliste %s', vaktliste.pk)
        rad.feil = str(exc)[:500] or exc.__class__.__name__
    rad.save()
    return rad


def signatur(grupper, brannliste=None) -> str:
    """SHA-256 over det fila bærer — ikke over fila, som har «laget»-tida i
    seg og derfor aldri er lik seg selv.

    **Brannlista er med når den finnes** (25. sep. 2026), så en ny plassering
    gir en ny utsending når «bare ved endringer» står på. Uten plasseringer
    er signaturen den samme som før, så lister uten overnatting sendes ikke
    på nytt bare fordi koden ble oppdatert.
    """
    import hashlib
    import json
    innhold = {'grupper': grupper, 'brannliste': brannliste} if brannliste else grupper
    return hashlib.sha256(
        json.dumps(innhold, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def send_planlagte(naa=None) -> list:
    """Intervallsendingen (13. sep. 2026): for hver liste i drift, send på
    nytt når intervallet er gått siden forrige utsending — og, når admin har
    satt «bare ved endringer», bare hvis lista har endret seg siden den sist
    ble *sendt*.

    Forrige utsending teller uansett hva som utløste den og om den gikk: et
    forsøk som feilet skal ikke gi et nytt forsøk hvert minutt mens
    e-posttjenesten er nede. Uendret liste gir ingen rad — det er ikke en
    hendelse, det er fravær av en.

    Returnerer radene som ble skrevet. Kaster ikke.
    """
    from . import services

    minutter = intervall_minutter()
    if not minutter or not mottakere():
        return []
    naa = naa or timezone.now()
    ut = []
    for vl in services.lister_i_drift().select_related('vakt'):
        siste = vl.utsendinger.first()
        if siste is not None and (naa - siste.created_at) < timedelta(minutes=minutter):
            continue
        if bare_ved_endring():
            sist_sendt = vl.utsendinger.filter(feil='').first()
            if sist_sendt is not None and sist_sendt.innhold_sha256 == signatur(
                    rader_for(vl), overnatting.brannliste(vl)):
                continue
        ut.append(send_fil(vl, utloest=Utsending.INTERVALL))
    return ut


def utsending_til_dict(rad):
    if rad is None:
        return None
    return {
        'id': rad.pk,
        'sendt_at': rad.created_at.isoformat(),
        'sendt_av': rad.sendt_av_navn,
        'utloest': rad.utloest,
        'antall_mottakere': rad.antall_mottakere,
        'antall_rader': rad.antall_rader,
        'feil': rad.feil,
    }
