"""KO-loggens frie felt i sladdingen (`core/sladding.py`, fase 7, 18. okt. 2026).

| Felt | Sladdet betyr |
|---|---|
| `Logglinje.tekst` | **Det samme som «Fjern»** (`services.fjern`): hele kjeden tømmes, og linja står med «fjernet av». KO hadde begrepet fra før; det som manglet var søket på tvers og registeret |
| `Hendelse.tittel` | «[Sladdet]» — en hendelse må ha en tittel. **Kopiene i systemlinjene** («H14 opprettet · Ola besvimt») sladdes med, også titler hendelsen hadde før den ble omdøpt |
| `Hendelse.melder` | Tom |

Den frosne vaktstatistikken bærer kopier av tittelen og siste linje (`ko/statistikk.py`,
«verken»-lista) — de sladdes med `core.sladding.skrubb_frosne`.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Q

from core.sladding import SLADDET, BaseSladdHandler, Funn, skrubb_frosne

HENDELSE = 'ko.hendelse'


def _hvor(vakt, nr=None) -> str:
    deler = [f'H{nr}'] if nr else []
    if vakt is not None:
        deler.append(vakt.navn)
        if vakt.portal_id:
            deler.append(vakt.portal.navn)
    return ' · '.join(deler)


class KoSladdHandler(BaseSladdHandler):
    slug = 'ko'
    etikett = 'KO-loggen'
    felt = {'ko.logglinje': ('tekst',), HENDELSE: ('tittel', 'melder')}

    def sok(self, q):
        from .models import Hendelse, Logglinje

        funn = [
            Funn('ko.logglinje', l.pk, 'tekst', 'Logglinje', l.tekst,
                 _hvor(l.vakt, getattr(l.hendelse, 'hendelsesnummer', None)), l.tidspunkt)
            # Systemlinjene har ingen `tekst` — de bygges av `systemdata` — så de treffes ikke.
            for l in (Logglinje.objects.filter(tekst__icontains=q)
                      .select_related('vakt__portal', 'hendelse').order_by('-tidspunkt'))
        ]
        for h in (Hendelse.objects.filter(Q(tittel__icontains=q) | Q(melder__icontains=q))
                  .select_related('vakt__portal').order_by('-opprettet_at')):
            for felt, navn in (('tittel', 'Hendelsens tittel'), ('melder', 'Melder')):
                verdi = getattr(h, felt)
                if q.casefold() in verdi.casefold() and verdi != SLADDET:
                    funn.append(Funn(HENDELSE, h.pk, felt, navn, verdi,
                                     _hvor(h.vakt, h.hendelsesnummer), h.opprettet_at))
        return funn

    def sladd(self, modell, pk, felt, *, bruker):
        from . import services
        from .models import Hendelse, Logglinje

        if modell == HENDELSE:
            hendelse = Hendelse.objects.filter(pk=pk).first()
            if hendelse is None:
                raise ValidationError('Hendelsen finnes ikke.')
            _sladd_hendelse(hendelse, felt)
            return [(HENDELSE, pk, felt)]
        linje = Logglinje.objects.filter(pk=pk).first()
        if linje is None:
            raise ValidationError('Linja finnes ikke.')
        # `fjern` fører kjeden i registeret med sin egen grunn; `core.sladding.sladd` fører
        # den på nytt med admins. Radene er de samme.
        services.fjern(linje, bruker=bruker)
        return [(modell, r.pk, 'tekst')
                for r in Logglinje.objects.filter(services._kjeden_q(linje.rot or linje))
                .exclude(kilde=services.KILDE_SYSTEM)]

    def gjenta(self, rad):
        from . import services
        from .models import Hendelse, Logglinje

        if rad.modell == HENDELSE:
            hendelse = Hendelse.objects.filter(pk=rad.rad_id).first()
            if hendelse is None:
                return False
            _sladd_hendelse(hendelse, rad.felt)
            return True
        linje = Logglinje.objects.filter(pk=rad.rad_id).first()
        if linje is None:
            return False
        if linje.tekst or linje.fjernet_at is None:
            services.tom_linje(linje, tid=linje.fjernet_at or rad.sladdet_at,
                               bruker=linje.fjernet_av or rad.av,
                               navn=linje.fjernet_av_navn or rad.av_navn)
        return True


def _sladd_hendelse(hendelse, felt) -> None:
    from .models import KILDE_SYSTEM, Logglinje

    if felt == 'melder':
        if hendelse.melder:
            hendelse.melder = ''
            hendelse.versjon += 1
            hendelse.save(update_fields=['melder', 'versjon'])
        return
    # Systemlinjene til hendelsen bærer tittelen frosset — også de den hadde før en omdøping.
    # Hver av dem peker på hendelsen (`systemlinje(..., hendelse=hendelse)` i services).
    linjer = Logglinje.objects.filter(hendelse=hendelse, kilde=KILDE_SYSTEM)
    titler = {hendelse.tittel}
    for linje in linjer:
        data = linje.systemdata or {}
        if data.get('tittel') not in (None, '', SLADDET):
            titler.add(data['tittel'])
            linje.systemdata = {**data, 'tittel': SLADDET}
            linje.save(update_fields=['systemdata'])
    skrubb_frosne(hendelse.vakt_id, titler - {SLADDET})
    if hendelse.tittel != SLADDET:
        hendelse.tittel = SLADDET
        hendelse.versjon += 1
        hendelse.save(update_fields=['tittel', 'versjon'])


def register_handlers() -> None:
    from core import sladding

    sladding.register(KoSladdHandler())

