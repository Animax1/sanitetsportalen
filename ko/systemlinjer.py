"""Hvilke systemhendelser løftes inn i KO-loggen — lista, og regelen bak den.

Besluttet med André 17. sep. 2026 (`docs/FORSLAG_KO.md` §11.1, `TODO.md`).
**Dette er en inkluderingsliste, og det er motsatt av `NOKLER_UTEN_AUDIT`** —
med vilje. Der er poenget at en ny nøkkel logges som standard, fordi en teller
for mye er støy mens en innstilling for lite er et hull man oppdager et år
senere. Her er det omvendt: loggen er et **dokument et menneske leser**, og en
hendelse for mye koster lesbarheten til alle de andre. §4.2 sier det rett ut —
systemhendelser løftes inn **kuratert, ikke automatisk**.

## Regelen, i tre setninger

1. **Løft det som endrer situasjonen, ikke det som endrer oppsettet.** En
   systemlinje skal svare på et spørsmål man stiller mens man leser loggen i
   etterkant: *hvorfor sto det stille i tolv minutter her?* En omdøpt
   enhetstype svarer aldri på det. Det er §4.2 sitt eget eksempel, ordrett.
2. **Løft hendelsen, ikke feltet.** `audit/` fører feltendringer, og det er
   riktig sted for dem. Loggen skal ha subjekt og verb: «Haugesund 56:
   Fremme».
3. **Én linje per ting som skjedde, ikke én per skriving.** Derfor bærer
   `enhet_avbrot` flagget `trenger_ressurs` i stedet for at «trenger ny
   ressurs» blir en linje til — de to er én hendelse sett fra hver sin side, og
   to linjer ville lest som to ting.

## Det som **ikke** løftes, og hvorfor

| Ikke løftet | Hvorfor |
|---|---|
| Lokasjoner, enhetstyper, problemstillinger opprettet/omdøpt/deaktivert | Oppsett, ikke situasjon (regel 1) |
| Feltendringer på oppdraget — fritekst rettet, problemstilling byttet | `audit/` gjør dette på feltnivå. En logg som får en linje hver gang noen retter en skrivefeil, slutter å bli lest |
| Innlogging, utlogging, sesjoner, MFA | Sikkerhet, ikke situasjon. Sidebaren svarer alt på hvem som har KO oppe |
| Modul av/på, portalinnstillinger, backup, gjenoppretting | Drift. Står i `audit/` og på `/portal-admin/server-status/` |
| Pasientregistreringer | Krysser registergrensen (§9.7). Loggen skal ikke bli en del av pasientjournalen |
| Vaktlistas stemplinger inn/ut | **Grensesaken, og svaret er «ikke nå».** «Lag 3 gikk av vakt» er ekte situasjonsinformasjon, men per-person-stempling på hver vaktpost ville druknet loggen ved hvert vaktskifte. Tas opp i pulje 4, der lag-begrepet får et hjem — og da som ressursen, ikke som personen |

## Hvorfor det er signaler og ikke et register i `core`

Retningen er `ko` → `oppdrag`, håndhevet med AST i `ko/tests_avhengighet.py`.
Et push-register hadde krevd at `oppdrag/services.py` meldte fra, og
oppdragsmodulen skal ikke røres før pulje 5. Signaler leses **her**, i den
importerende modulen, og retningen holdes da av konstruksjonen.

Forbeholdet, som er ekte: **et signal ser raden, ikke intensjonen.** «Avbrutt
fordi ingen svarte» og «avbrutt fordi pasienten gikk hjem» er samme rad.
Trenger en linje intensjon, må det kallstedet dytte — og *da* bygges registeret,
ikke før.

**Fire av de ni kodene fantes allerede som `oppdrag.Enhetshendelse`.** Den
bærer `tatt_av`, `rykket_videre`, `avbrutt` og `avventer` med tidspunkt og
bruker. Det er den samme erfaringen som §2: før noe designes inn i KO, sjekk om
oppdragsmodulen allerede har begrepet.
"""
from __future__ import annotations

from django.utils import timezone

# `ko` → `oppdrag` er den tillatte retningen. Formen på oppdragsnummeret eies
# av oppdragsmodulen, og skrives ikke om her.
from oppdrag.services import oppdragsnr


# ── Kodene ───────────────────────────────────────────────────────────────────
#
# **Kode og data, ikke ferdig tekst.** Setningen bygges her ved lesing, slik at
# ordlyden kan rettes uten at historikken skrives om — som da «#45» ble «O45»
# 18. sep. 2026 (§6), uten en migrasjon. Det som *kan forsvinne* fryses
# derimot i `systemdata` ved skriving: enheten kan omdøpes, oppdraget slettes
# ved vaktarkivering, og en logg som mister subjektet sitt er verdiløs akkurat
# når den leses (§4.5, §4.7).

OPPDRAG_OPPRETTET = 'oppdrag_opprettet'
OPPDRAG_STATUS = 'oppdrag_status'
TIDSPUNKT_KORRIGERT = 'tidspunkt_korrigert'
ENHET_VARSLET = 'enhet_varslet'
ENHET_TATT_AV = 'enhet_tatt_av'
ENHET_RYKKET_VIDERE = 'enhet_rykket_videre'
ENHET_AVBROT = 'enhet_avbrot'
ENHET_AVVENTER = 'enhet_avventer'
VAKTMODUS = 'vaktmodus'
HENDELSE_OPPRETTET = 'hendelse_opprettet'
HENDELSE_LUKKET = 'hendelse_lukket'
HENDELSE_GJENAPNET = 'hendelse_gjenapnet'
HENDELSE_PRIORITET = 'hendelse_prioritet'
HENDELSE_LAG_PAA = 'hendelse_lag_paa'
HENDELSE_LAG_AV = 'hendelse_lag_av'
OPPDRAG_KNYTTET = 'oppdrag_knyttet'
TAVLE_FLYTTET = 'tavle_flyttet'
TAVLE_RETTET = 'tavle_rettet'

#: Hver kode med sin begrunnelse. Lista er kontrakten: en kode som ikke står
#: her, skrives ikke — `ko/tests_systemlinjer.py` håndhever begge veier, slik
#: at verken en ny kode eller en fjernet kode kan gli inn eller ut i stillhet.
KODER: dict[str, str] = {
    OPPDRAG_OPPRETTET:
        'Begynnelsen på et forløp. Uten den er statuslinjene under foreldreløse.',
    OPPDRAG_STATUS:
        'Kjernen. Det er disse som svarer på «hvor lenge sto det stille».',
    TIDSPUNKT_KORRIGERT:
        'Uten den ser tidslinja ut som om den alltid var slik. Egen linje, '
        'aldri en endring av den gamle — samme regel loggen selv har (§4.3).',
    ENHET_VARSLET:
        'Ressursbruk per hendelse. «Vi sendte to biler» står ikke lesbart noe '
        'annet sted.',
    ENHET_TATT_AV:
        'En ressurs som forsvinner fra oppdraget uten at noe sier fra, er en '
        'ressurs man tror man har.',
    ENHET_RYKKET_VIDERE:
        'Bilen dro til noe annet mens dette sto uferdig. Forklarer hullet.',
    ENHET_AVBROT:
        'Utfall, og oftest opptakten til at oppdraget trenger en ny ressurs.',
    ENHET_AVVENTER:
        'Hun sa på nødnett at hun ikke kan ta det nå. Nøyaktig tilstanden der '
        'en enhet blir glemt.',
    VAKTMODUS:
        'Forklarer hvorfor en bil ikke ble varslet.',
    # Hendelsene (pulje 5). Fire koder, og de er **operatørens handlinger**,
    # ikke løftet av et signal: KO-tjenestelaget skriver dem selv, og fryser
    # operatøren som forfatter — «H12 lukket» uten hvem er en linje som ikke
    # svarer på det man leser loggen for.
    HENDELSE_OPPRETTET:
        'Begynnelsen på en hendelse. En hendelse begynner når noen sier noe '
        'over samband, ofte lenge før et oppdrag finnes.',
    HENDELSE_LUKKET:
        'Slutten — og om den ble lukket med åpne oppdrag, står det på linja. '
        'Det er tilstanden der en enhet blir glemt (§4.6).',
    HENDELSE_GJENAPNET:
        'En lukking som var en misforståelse eller et feilklikk (André, '
        '18. sep. 2026). Egen linje, aldri en stille statusendring.',
    OPPDRAG_KNYTTET:
        'Hvilke oppdrag som hørte til hvilken hendelse, med flyttinger. '
        'Grupperingen på tavla forsvinner når vakta arkiveres; loggen står.',
    HENDELSE_PRIORITET:
        '«H14 satt til Viktig av Kari» er en avgjørelse, ikke en feltendring '
        '(18. sep. 2026): det er den man leter etter når man spør hvorfor to '
        'biler ble sendt. Aldri en stille oppdatering.',
    HENDELSE_LAG_PAA:
        'Lagene får oppdrag muntlig på samband og registreres på hendelsen '
        '(André, 19. sep. 2026). «Lag 2 registrert på H14» er den ene linja '
        'som sier hvor laget ble sendt — det stempler aldri selv.',
    HENDELSE_LAG_AV:
        'Motstykket: laget er ledig igjen. Uten den ser kortet ledig ut mens '
        'loggen fortsatt sier at det er på H14.',
    # Tavla (22. sep. 2026). Operatørens handling, skrevet av `ko/tavle.py`
    # med hvem — per **ressurs**, ikke per person: det er lagene som flyttes,
    # og en linje per mannskap ville druknet loggen ved hvert vaktskifte.
    TAVLE_FLYTTET:
        '«Lag 3 → Parkscene» er det tavla på veggen aldri kunne si: når, og '
        'hvem som flyttet. Forklarer hullene i «hvem har vært på Parkscene».',
    TAVLE_RETTET:
        'En retting skriver om historikken «Besøk» teller. Uten en linje ville '
        'tallene endret seg uten at noen kunne si hvorfor — samme grunn som '
        'TIDSPUNKT_KORRIGERT.',
}


# ── Tegning ──────────────────────────────────────────────────────────────────

def _enhet(data) -> str:
    return data.get('enhet') or 'Ukjent enhet'


def _oppdrag(data) -> str:
    """Oppdragsnummeret slik det sies: `O45` (§6, fra 18. sep. 2026).

    Formen eies av oppdragsmodulen (`oppdrag.services.oppdragsnr`), og byttet
    fra `#45` traff hele historikken uten en migrasjon — det er grunnen til at
    systemlinjer lagres som kode + data.
    """
    nummer = data.get('oppdragsnummer')
    return oppdragsnr(nummer) if nummer else 'oppdrag'


def hendelsesnr(nummer) -> str:
    """`H12` — hendelsesnummeret der plassen er trang (§6). Tvillingen av
    `oppdragsnr`, og den ene formen KO selv eier."""
    return f'H{nummer}'


def _hendelse(data, nokkel='hendelsesnummer') -> str:
    nummer = data.get(nokkel)
    return hendelsesnr(nummer) if nummer else 'hendelse'


def tegn(kode: str, data: dict) -> str:
    """Setningen for én systemlinje. Aldri fritekst, aldri brukerdata.

    Returnerer en tom streng for en ukjent kode i stedet for å kaste: en rad
    skrevet av en nyere versjon skal ikke ta ned loggen for den som leser den
    med en eldre. Linja står da med tidspunkt og kilde, som er nok til å se at
    noe skjedde.
    """
    data = data or {}
    if kode == OPPDRAG_OPPRETTET:
        deler = [f'{_oppdrag(data)} opprettet', data.get('problemstilling') or '']
        if data.get('hastegrad'):
            deler.append(data['hastegrad'])
        if data.get('lokasjon'):
            deler.append(data['lokasjon'])
        return ' · '.join(d for d in deler if d)
    if kode == OPPDRAG_STATUS:
        linje = f'{_enhet(data)}: {data.get("status_navn") or "?"} ({_oppdrag(data)})'
        if data.get('fort_av_ko'):
            # §4.6: «det skal stå i sporet at KO avsluttet på enhetens vegne».
            linje += ' — ført av KO'
        if data.get('forsinket'):
            linje += ' — meldt forsinket'
        return linje
    if kode == TIDSPUNKT_KORRIGERT:
        return (f'{_enhet(data)}: {data.get("status_navn") or "?"} rettet fra '
                f'{data.get("fra") or "?"} til {data.get("til") or "?"} '
                f'({_oppdrag(data)})')
    if kode == ENHET_VARSLET:
        linje = f'{_enhet(data)} varslet på {_oppdrag(data)}'
        if data.get('modus') == 'passiv':
            linje += ' (passiv vakt)'
        return linje
    if kode == ENHET_TATT_AV:
        return f'{_enhet(data)} tatt av {_oppdrag(data)}'
    if kode == ENHET_RYKKET_VIDERE:
        linje = f'{_enhet(data)} rykket videre fra {_oppdrag(data)}'
        if data.get('detalj'):
            linje += f' til {data["detalj"]}'
        return linje + _trenger(data)
    if kode == ENHET_AVBROT:
        return f'{_enhet(data)} avbrøt {_oppdrag(data)}' + _trenger(data)
    if kode == ENHET_AVVENTER:
        return f'{_enhet(data)} avventer {_oppdrag(data)}'
    if kode == VAKTMODUS:
        navn = 'passiv vakt' if data.get('modus') == 'passiv' else 'aktiv vakt'
        return f'{_enhet(data)} satt i {navn}'
    if kode == HENDELSE_OPPRETTET:
        deler = [f'{_hendelse(data)} opprettet', data.get('tittel') or '',
                 data.get('lokasjon') or '']
        # Prioriteten står på linja bare når den sier noe — Grønn er
        # normaltilstanden, og et merke på hver hendelse er støy.
        if data.get('prioritet') and data['prioritet'] != 'Grønn':
            deler.append(data['prioritet'])
        # Lagene som ble valgt i skjemaet står her, ikke som én linje hver.
        lag = data.get('lag') or []
        if lag:
            deler.append('lag: ' + ', '.join(str(l) for l in lag))
        return ' · '.join(d for d in deler if d)
    if kode == HENDELSE_LAG_PAA:
        linje = f'{data.get("lag") or "Lag"} registrert på {_hendelse(data)}'
        if data.get('tittel'):
            linje += f' · {data["tittel"]}'
        return linje
    if kode == HENDELSE_LAG_AV:
        return f'{data.get("lag") or "Lag"} tatt av {_hendelse(data)}'
    if kode == HENDELSE_PRIORITET:
        linje = f'{_hendelse(data)} satt til {data.get("prioritet") or "?"}'
        if data.get('fra_prioritet'):
            linje += f' (var {data["fra_prioritet"]})'
        if data.get('tittel'):
            linje += f' · {data["tittel"]}'
        return linje
    if kode == HENDELSE_LUKKET:
        linje = f'{_hendelse(data)} lukket'
        if data.get('tittel'):
            linje += f' · {data["tittel"]}'
        apne = data.get('apne_oppdrag') or 0
        if apne:
            # §4.6: døra hun åpnet bevisst skal stå i sporet.
            linje += f' — med {apne} åpne oppdrag' if apne > 1 else ' — med 1 åpent oppdrag'
        return linje
    if kode == HENDELSE_GJENAPNET:
        linje = f'{_hendelse(data)} åpnet igjen'
        if data.get('tittel'):
            linje += f' · {data["tittel"]}'
        return linje
    if kode == TAVLE_FLYTTET:
        hvem = data.get('ressurs') or 'Ressurs'
        til, fra = data.get('til') or '', data.get('fra') or ''
        if not til:
            return f'{hvem} uten plass' + (f' (var {fra})' if fra else '')
        return f'{hvem} → {til}' + (f' (fra {fra})' if fra else '')
    if kode == TAVLE_RETTET:
        hvem = data.get('ressurs') or 'Ressurs'
        sted = data.get('sted') or ''
        periode = '–'.join(t for t in (data.get('fra_foer') or '', data.get('til_foer') or '') if t)
        if data.get('fjernet'):
            return f'{hvem} {sted} {periode} fjernet fra tavla'.replace('  ', ' ')
        deler = []
        for felt, navn in (('fra', 'fra'), ('til', 'til')):
            foer, etter = data.get(f'{felt}_foer') or '', data.get(felt) or ''
            if foer != etter:
                deler.append(f'{navn} {foer or "–"} → {etter or "–"}')
        return f'{hvem} {sted} rettet: ' + ', '.join(deler)
    if kode == OPPDRAG_KNYTTET:
        fra = data.get('fra_hendelsesnummer')
        til = data.get('hendelsesnummer')
        if til and fra:
            return f'{_oppdrag(data)} flyttet fra {hendelsesnr(fra)} til {hendelsesnr(til)}'
        if til:
            return f'{_oppdrag(data)} knyttet til {hendelsesnr(til)}'
        if fra:
            return f'{_oppdrag(data)} løsnet fra {hendelsesnr(fra)}'
        return f'{_oppdrag(data)} knyttet til hendelse'
    return ''


def _trenger(data) -> str:
    """Regel 3: flagget på linja, ikke en linje til.

    «Trenger ny ressurs» og «enheten avbrøt» er én hendelse sett fra hver sin
    side. To linjer ville lest som to ting som skjedde.
    """
    return ' — oppdraget trenger ny ressurs' if data.get('trenger_ressurs') else ''


def klokkeslett(tid) -> str:
    """`HH:MM` i lokal tid, for `systemdata`.

    Lokal tid og ikke UTC fordi verdien er **frosset tekst** i en setning et
    menneske leser, ikke et tidspunkt noe regner på. Det regnbare tidspunktet
    står i `Logglinje.tidspunkt`.
    """
    return timezone.localtime(tid).strftime('%H:%M') if tid else ''
