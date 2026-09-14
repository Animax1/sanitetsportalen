"""Tallene backup-siden viser — samlet ett sted, uten HTTP.

Viewet skal lese denne og tegne. Grunnen til at det er en egen modul og ikke
kode inne i viewet, er at «verste tilfelle» (§2.5 i
`docs/PLAN_BACKUP_OMLEGGING.md`) er et regnestykke med en regel i seg som må
kunne testes uten å gå veien om en innlogget klient.
"""
from __future__ import annotations

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Over dette er volumet i ferd med å bli fullt, og et fullt volum stopper
#: backupen uten at noe annet i portalen merker det.
DISK_ADVARSEL_PROSENT = 80


def verste_tilfelle() -> dict:
    """Hvor mye arbeid som går tapt per modul hvis Railway forsvinner nå.

    **Målt mot siste vellykkede opplasting til Scaleway, ikke mot siste fil på
    volumet.** Er volumet borte, er det bare bucketen som teller. En linje som
    leste volumet ville vist fire minutter mens den virkelige avstanden var to
    dager, fordi opplastingene hadde feilet siden i forgårs — og det er
    nettopp den situasjonen tallet finnes for å avsløre.

    Uten offsite konfigurert (staging og lokalt) finnes ingen kopi utenfor
    Railway. Da måles det mot volumet i stedet, og svaret sier `offsite: False`
    så visningen kan si hva den faktisk viser framfor å påstå noe den ikke vet.
    """
    from core import offsite
    from core.backup import all_handlers
    from core.models import OffsiteKopi
    from core.models import Backup

    har_offsite = offsite.er_konfigurert()
    na = timezone.now()

    rader = []
    for handler in all_handlers():
        if handler.slug == 'full':
            continue   # dekker alt; ville dublert hver modul i lista
        if har_offsite:
            tid = (OffsiteKopi.objects
                   .filter(module_slug=handler.slug, feil='')
                   .exclude(sendt_at=None)
                   .order_by('-sendt_at')
                   .values_list('sendt_at', flat=True).first())
        else:
            tid = (Backup.objects
                   .filter(module_slug=handler.slug)
                   .order_by('-created_at')
                   .values_list('created_at', flat=True).first())
        rader.append({
            'slug': handler.slug,
            'navn': handler.display_name or handler.slug,
            'tid': tid,
            'minutter': None if tid is None else int((na - tid).total_seconds() // 60),
        })

    kjente = [r['minutter'] for r in rader if r['minutter'] is not None]
    return {
        'offsite': har_offsite,
        'rader': rader,
        'verste_minutter': max(kjente) if kjente else None,
        'mangler': [r['navn'] for r in rader if r['tid'] is None],
    }


def fmt_alder(minutter) -> str:
    """«4 min», «6 t», «2 d». Tallet skal kunne leses i et øyekast."""
    if minutter is None:
        return 'aldri'
    if minutter < 60:
        return f'{minutter} min'
    if minutter < 1440:
        return f'{minutter // 60} t'
    return f'{minutter // 1440} d'


def diskbruk() -> dict:
    """Volumet backupene ligger på — brukt, ledig, og hvor mye som er backup.

    Railway-volumet er 5 GB og fast. **Et fullt volum stopper backupen**, og
    ingenting annet i portalen merker det før noe annet også må skrive. Derfor
    står tallet på siden ved siden av cap-innstillingene som styrer det.
    """
    import shutil

    from core.backup import get_backup_dir

    try:
        sti = get_backup_dir()
        st = shutil.disk_usage(sti)
        brukt = st.total - st.free
        backup_bytes = sum(p.stat().st_size for p in sti.iterdir() if p.is_file())
        prosent = round(100 * brukt / st.total, 1) if st.total else None
        return {
            'sti': str(sti),
            'total_mb': round(st.total / 1048576, 1),
            'brukt_mb': round(brukt / 1048576, 1),
            'ledig_mb': round(st.free / 1048576, 1),
            'brukt_prosent': prosent,
            'backup_mb': round(backup_bytes / 1048576, 1),
            'trangt': prosent is not None and prosent >= DISK_ADVARSEL_PROSENT,
        }
    except Exception as exc:   # noqa: BLE001 — et kort som feiler er borte
        logger.warning('backup-oversikt: kunne ikke lese diskbruk: %s', exc)
        return {'error': str(exc)[:200]}


def modulrader(plan_form_klasse=None) -> list[dict]:
    """Én rad per registrert handler, med plan, filer og størrelse.

    Filene hentes med to spørringer for alle modulene til sammen, ikke to per
    modul: siden viser seks moduler, og en spørring per rad per felt blir tjue
    før man har tenkt på det.
    """
    from django.db.models import Count, Sum

    from core.backup import all_handlers
    from core.models import Backupplan
    from core.models import Backup

    Backupplan.standardplanen()
    tall = {
        r['module_slug']: r for r in Backup.objects
        .values('module_slug')
        .annotate(antall=Count('id'), bytes=Sum('size_bytes'))
    }

    rader = []
    for handler in all_handlers():
        if handler.slug == Backupplan.FULL_SLUG:
            continue   # egen boks øverst; se `sideinnhold()`
        plan = Backupplan.hent(handler.slug)
        t = tall.get(handler.slug, {})
        rader.append({
            'slug': handler.slug,
            'navn': handler.display_name or handler.slug,
            'plan': plan,
            'gjeldende': plan.gjeldende(),
            'antall': t.get('antall', 0),
            'mb': round((t.get('bytes') or 0) / 1048576, 1),
            'form': plan_form_klasse(instance=plan, prefix=handler.slug)
            if plan_form_klasse else None,
            'filer': list(Backup.objects.filter(module_slug=handler.slug)
                          .order_by('-created_at')[:20]),
        })
    return rader


def helrad(plan_form_klasse=None) -> dict | None:
    """Kortet for den hele databasen, eller None om handleren ikke er
    registrert. Skilt fra modulradene fordi den er en annen slags fil: den
    dekker alt, har egen frist offsite, og gjenopprettingen rører kontoen du
    er logget inn med."""
    from django.db.models import Count, Sum

    from core.backup import get_handler
    from core.models import Backupplan
    from core.models import Backup

    handler = get_handler(Backupplan.FULL_SLUG)
    if handler is None:
        return None

    plan = Backupplan.hent(Backupplan.FULL_SLUG)
    tall = (Backup.objects.filter(module_slug=Backupplan.FULL_SLUG)
            .aggregate(antall=Count('id'), bytes=Sum('size_bytes')))
    return {
        'slug': plan.slug,
        'navn': handler.display_name,
        'plan': plan,
        'gjeldende': plan,
        'antall': tall['antall'] or 0,
        'mb': round((tall['bytes'] or 0) / 1048576, 1),
        'form': plan_form_klasse(instance=plan, prefix=plan.slug)
        if plan_form_klasse else None,
        'filer': list(Backup.objects.filter(module_slug=Backupplan.FULL_SLUG)
                      .order_by('-created_at')[:10]),
    }


def sideinnhold(plan_form_klasse=None) -> dict:
    """Alt siden trenger, i én dict."""
    from core import offsite
    from core.backup.klokke import TIKK_SEKUNDER, vakthund
    from core.models import Backupplan

    advarsler = vakthund()
    return {
        'hel': helrad(plan_form_klasse),
        'standard': Backupplan.standardplanen(),
        'standard_form': (plan_form_klasse(instance=Backupplan.standardplanen(),
                                           prefix='standard')
                          if plan_form_klasse else None),
        'rader': modulrader(plan_form_klasse),
        'rpo': verste_tilfelle(),
        'disk': diskbruk(),
        'offsite': offsite.status(),
        'vakthund': advarsler,
        'tikk_sekunder': TIKK_SEKUNDER,
    }
