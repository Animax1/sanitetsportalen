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


# ── Kodene ───────────────────────────────────────────────────────────────────
#
# **Kode og data, ikke ferdig tekst.** Setningen bygges her ved lesing, slik at
# ordlyden kan rettes uten at historikken skrives om — «O45» i stedet for «#45»
# når pulje 3 innfører nummerserien, jf. §6. Det som *kan forsvinne* fryses
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
RESSURS_STATUS = 'ressurs_status'

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
    RESSURS_STATUS:
        'KO-ført status på en ressurs som ikke stempler selv (§3.1). **Den '
        'tiende koden, og den første som ikke løftes av et signal:** dette er '
        'KOs egen handling, så tjenesten skriver linja direkte. Uten den '
        'ligger historikken bare i én kolonne som overskrives, og «hvor lenge '
        'sto lag 3 ute av drift» har ikke noe svar.',
}


# ── Tegning ──────────────────────────────────────────────────────────────────

def _enhet(data) -> str:
    return data.get('enhet') or 'Ukjent enhet'


def _oppdrag(data) -> str:
    """Oppdragsnummeret slik det sies. `#45` i dag; `O45` fra pulje 3 (§6).

    Formen står **ett sted** nettopp fordi den skal byttes: i en logg der
    hendelses- og oppdragsnumre står på nabolinjer er `#45` ikke utvetydig, og
    det er i loggen de møtes.
    """
    nummer = data.get('oppdragsnummer')
    return f'#{nummer}' if nummer else 'oppdrag'


def _ressurs(data) -> str:
    """Navnet ressursen hadde da linja ble skrevet.

    Frosset i `systemdata`, ikke slått opp: en `Ressurs` henger på én
    vaktliste med `CASCADE` (§3.1), så rada er borte neste sesong mens linja
    skal stå i 730 dager. Samme regel som enhetsnavnet.
    """
    return data.get('ressurs') or 'Ukjent ressurs'


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
    if kode == RESSURS_STATUS:
        linje = f'{_ressurs(data)}: {data.get("status_navn") or "?"}'
        # «Ført av KO» står alltid på denne koden — den *finnes* bare for dem
        # som ikke melder selv (§3.1), og skillet «bilen sa det» mot «KO førte
        # det» skal være synlig i loggen og ikke utledes av hvilken kode det er.
        return linje + ' — ført av KO'
    if kode == VAKTMODUS:
        navn = 'passiv vakt' if data.get('modus') == 'passiv' else 'aktiv vakt'
        return f'{_enhet(data)} satt i {navn}'
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
