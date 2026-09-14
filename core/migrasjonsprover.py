"""Prøver som kjører én migrasjon mot PostgreSQL **med rader i basen**.

**Hvorfor dette ikke er det samme som å kjøre testsuiten mot PostgreSQL.**
Djangos testrunner lager testbasen ved å kjøre alle migrasjonene mot en *tom*
base. Et `RunPython`-steg som skal flytte data finner da ingenting å flytte,
skriver ingenting, og legger ingen triggerhendelser i kø — så migrasjonen som
tok ned deployen 30. aug. 2026 ville gått rett gjennom. Feilen krever tre ting
samtidig: PostgreSQL, rader, og en skjemaendring etter skrivingen. Suiten kan
gi det første. Denne fila gir de to andre.

Hver prøve er tre ting:

    foregaaende  hvilken migrasjon basen settes til før prøven
    seed         rå SQL som legger inn rader i den *historiske* formen
    sjekk        rå SQL som leser hva migrasjonen faktisk gjorde

**Rå SQL, ikke modellklasser.** Modellene har den nye formen; tabellene har
den gamle. Bruker man ORM-en til å seede, skriver man mot kolonner som ikke
finnes ennå, og prøven feiler på seg selv i stedet for på migrasjonen.

Registeret håndheves av `myproject/tests_migrations.py`: en migrasjon som
skriver rader og deretter endrer skjema, må ha en prøve her — ellers er den
bare påstått trygg.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Migrasjonsprove:
    """Én migrasjon, prøvd mot PostgreSQL med rader i basen."""

    migrasjon: str          # 'vaktliste.0007_...' — app + navn
    foregaaende: str        # migrasjonsnavnet basen settes til først
    beskrivelse: str
    seed: Callable          # (cursor) -> None
    sjekk: Callable         # (cursor) -> None, kaster AssertionError

    @property
    def app(self) -> str:
        return self.migrasjon.split('.', 1)[0]


# ── vaktliste.0007 ───────────────────────────────────────────────────────────

def _seed_0007(c):
    """Verden slik staging så ut: to ressurser i hver sin type, én rolle."""
    c.execute("""INSERT INTO core_vakt (navn, year, startet, er_aktiv)
                 VALUES ('Proevevakt', 2026, now(), false) RETURNING id""")
    vakt = c.fetchone()[0]
    c.execute("""INSERT INTO vaktliste_vaktliste
                 (created_at, updated_at, status, notat, vakt_id)
                 VALUES (now(), now(), 'planlegging', '', %s) RETURNING id""", [vakt])
    vl = c.fetchone()[0]

    ressurser = {}
    for navn, type_ in (('Ambulanse 1', 'ambulanse'), ('Samleplass', 'samleplass'),
                        ('Rar', 'finnes-ikke')):
        c.execute("""INSERT INTO vaktliste_ressurs
                     (created_at, updated_at, navn, type, rekkefolge, vaktliste_id)
                     VALUES (now(), now(), %s, %s, 10, %s) RETURNING id""",
                  [navn, type_, vl])
        ressurser[navn] = c.fetchone()[0]

    c.execute("""INSERT INTO vaktliste_korps (created_at, updated_at, navn, kortnavn, er_aktiv)
                 VALUES (now(), now(), 'Haugesund', 'HGSD', true) RETURNING id""")
    korps = c.fetchone()[0]
    c.execute("""INSERT INTO vaktliste_mannskap
                 (created_at, updated_at, navn, telefon, er_aktiv, notat, korps_id)
                 VALUES (now(), now(), 'Kari', '', true, '', %s) RETURNING id""", [korps])
    kari = c.fetchone()[0]

    # Én aktiv og én pensjonert rolle: begge skal følge med til hver gruppe,
    # og `er_aktiv` skal overleve kopieringen.
    roller = {}
    for navn, aktiv in (('Lagleder', True), ('Utgaatt', False)):
        c.execute("""INSERT INTO vaktliste_ressursrolle (created_at, updated_at, navn, er_aktiv)
                     VALUES (now(), now(), %s, %s) RETURNING id""", [navn, aktiv])
        roller[navn] = c.fetchone()[0]

    # To skift på hver sin ressurstype, med samme rolle — det er nettopp her
    # kopiene må skille lag, og der triggerkøen fylles opp.
    for res in ('Ambulanse 1', 'Samleplass'):
        c.execute("""INSERT INTO vaktliste_vaktpost
                     (created_at, updated_at, fra_tid, til_tid, merknad,
                      mannskap_id, ressurs_id, rolle_id)
                     VALUES (now(), now(), now(), now() + interval '8 hours', '',
                             %s, %s, %s)""", [kari, ressurser[res], roller['Lagleder']])
    # Og en ledig plass med den utgåtte rollen.
    c.execute("""INSERT INTO vaktliste_vaktpost
                 (created_at, updated_at, fra_tid, til_tid, merknad,
                  mannskap_id, ressurs_id, rolle_id)
                 VALUES (now(), now(), now(), now() + interval '8 hours', '',
                         NULL, %s, %s)""",
              [ressurser['Ambulanse 1'], roller['Utgaatt']])


def _sjekk_0007(c):
    """Kom dataene riktig over — ikke bare «gikk migrasjonen gjennom»."""
    c.execute('SELECT navn FROM vaktliste_ressursgruppe ORDER BY rekkefolge')
    grupper = [r[0] for r in c.fetchall()]
    assert grupper == ['Samleplass', 'Mannskapsbil', 'Ambulanse', 'Lag', 'KO', 'Annet'], \
        f'standardgruppene mangler eller er i feil rekkefølge: {grupper}'

    c.execute("""SELECT r.navn, g.navn FROM vaktliste_ressurs r
                 JOIN vaktliste_ressursgruppe g ON g.id = r.gruppe_id
                 ORDER BY r.navn""")
    par = dict(c.fetchall())
    assert par['Ambulanse 1'] == 'Ambulanse', par
    assert par['Samleplass'] == 'Samleplass', par
    assert par['Rar'] == 'Annet', f'ukjent type skal falle til Annet, ikke {par["Rar"]!r}'

    # Hver rolle er kopiert til hver gruppe, og `er_aktiv` fulgte med.
    c.execute("""SELECT navn, count(*), bool_and(er_aktiv)
                 FROM vaktliste_ressursrolle GROUP BY navn ORDER BY navn""")
    roller = {n: (antall, aktiv) for n, antall, aktiv in c.fetchall()}
    assert roller['Lagleder'] == (6, True), roller
    assert roller['Utgaatt'] == (6, False), roller

    # Selve poenget: hvert skift peker på sin egen ressurs' gruppe.
    c.execute("""SELECT count(*) FROM vaktliste_vaktpost vp
                 JOIN vaktliste_ressurs r ON r.id = vp.ressurs_id
                 JOIN vaktliste_ressursrolle rl ON rl.id = vp.rolle_id
                 WHERE rl.gruppe_id <> r.gruppe_id""")
    assert c.fetchone()[0] == 0, 'vaktposter peker på en annen gruppes rolle'

    c.execute("""SELECT count(*) FROM information_schema.columns
                 WHERE table_name = 'vaktliste_ressurs' AND column_name = 'type'""")
    assert c.fetchone()[0] == 0, 'den gamle type-kolonnen står igjen'

    c.execute("""SELECT attnotnull FROM pg_attribute
                 WHERE attrelid = 'vaktliste_ressurs'::regclass AND attname = 'gruppe_id'""")
    assert c.fetchone()[0], 'ressurs.gruppe_id skulle vært NOT NULL'

    c.execute("""SELECT count(*) FROM pg_constraint
                 WHERE conrelid = 'vaktliste_ressursrolle'::regclass
                   AND conname = 'unikt_rollenavn_per_gruppe'""")
    assert c.fetchone()[0] == 1, 'unikhetsskranken per gruppe mangler'


# ── oppdrag.0011 ─────────────────────────────────────────────────────────────

def _seed_oppdrag_0011(c):
    """To oppdrag på hver sin enhet, med meldinger — slik prod ser ut før
    koblingsraden finnes. Det ene er ledig og i historikken."""
    c.execute("""INSERT INTO core_vakt (navn, year, startet, er_aktiv)
                 VALUES ('Proevevakt', 2026, now(), true) RETURNING id""")
    vakt = c.fetchone()[0]
    c.execute("""INSERT INTO oppdrag_lokasjon (created_at, updated_at, navn, er_aktiv, rekkefolge)
                 VALUES (now(), now(), 'Scene', true, 100) RETURNING id""")
    lok = c.fetchone()[0]
    enheter = {}
    for navn in ('HGSD 56', 'KARM 12'):
        c.execute("""INSERT INTO oppdrag_enhet (created_at, updated_at, navn, er_aktiv, pa_vakt)
                     VALUES (now(), now(), %s, true, true) RETURNING id""", [navn])
        enheter[navn] = c.fetchone()[0]

    oppdrag = {}
    for nr, navn, status, hist in ((1, 'HGSD 56', 'fremme', None),
                                   (2, 'KARM 12', 'ledig', 'now()')):
        c.execute(f"""INSERT INTO oppdrag_oppdrag
                     (created_at, updated_at, oppdragsnummer, problemstilling, hastegrad,
                      fritekst, status, grovsortering, vakt_id, enhet_id, lokasjon_id,
                      historikk_fra)
                     VALUES (now(), now(), %s, 'Fall', 'Haster', '', %s, '', %s, %s, %s,
                             {hist or 'NULL'}) RETURNING id""",
                  [nr, status, vakt, enheter[navn], lok])
        oppdrag[nr] = c.fetchone()[0]

    for nr, statuser in ((1, ('rykker_ut', 'fremme')), (2, ('rykker_ut', 'ledig'))):
        for st in statuser:
            c.execute("""INSERT INTO oppdrag_statusmelding
                         (created_at, updated_at, status, tidspunkt, forsinket, automatisk,
                          sted, oppdrag_id)
                         VALUES (now(), now(), %s, now(), false, false, '', %s)""",
                      [st, oppdrag[nr]])


def _sjekk_oppdrag_0011(c):
    c.execute("""SELECT o.oppdragsnummer, count(oe.id), min(oe.status), min(oe.enhet_id) = o.enhet_id
                 FROM oppdrag_oppdrag o LEFT JOIN oppdrag_oppdragsenhet oe ON oe.oppdrag_id = o.id
                 GROUP BY o.id ORDER BY o.oppdragsnummer""")
    rader = c.fetchall()
    assert [r[1] for r in rader] == [1, 1], f'nøyaktig én koblingsrad per oppdrag: {rader}'
    assert [r[2] for r in rader] == ['fremme', 'ledig'], f'status følger oppdraget: {rader}'
    assert all(r[3] for r in rader), f'koblingsraden peker på oppdragets enhet: {rader}'

    c.execute('SELECT count(*) FROM oppdrag_statusmelding WHERE oppdragsenhet_id IS NULL')
    assert c.fetchone()[0] == 0, 'meldinger uten koblingsrad'
    c.execute("""SELECT count(*) FROM oppdrag_statusmelding m
                 JOIN oppdrag_oppdragsenhet oe ON oe.id = m.oppdragsenhet_id
                 WHERE oe.oppdrag_id <> m.oppdrag_id""")
    assert c.fetchone()[0] == 0, 'melding pekt på feil oppdrags koblingsrad'


# ── core.0008–0010 (Backupplan) ──────────────────────────────────────────────

def _seed_backupplan(c):
    """Radene prod faktisk har i `core_modulebackupconfig`.

    Det er hele poenget med prøven: i en tom base finner `0009` ingenting å
    oversette, skriver ingenting, og går grønt uten å ha gjort noe. Her står
    de fem tilstandene som betyr noe — en modul som er på, en som står `av`
    med `enabled=False`, en som står av med `interval_minutes=0` (de to er
    ulike måter å si det samme på, og begge finnes), et intervall som går
    opp i timer, og ett som ikke gjør det.
    """
    rader = [
        # slug,            enabled, minutter, behold
        ('patients',       True,    60,       50),
        ('arkiv',          True,    360,      20),
        ('oppdrag',        False,   60,       50),   # av via enabled
        ('oppdrag_arkiv',  True,    0,        20),   # av via intervall
        ('vaktliste',      True,    45,       30),   # går ikke opp i timer
        ('dogn',           True,    1440,     7),
    ]
    # `ON CONFLICT`, ikke ren `INSERT`: migrasjonene `0002` og `0005` oppretter
    # selv radene for «patients» og «arkiv», så de står der alt når basen er
    # satt til `0007`. Det er også slik prod ser ut — seedede rader, noen av
    # dem etterpå redigert i grensesnittet — og prøven skal ligne på prod.
    for slug, enabled, minutter, behold in rader:
        c.execute("""INSERT INTO core_modulebackupconfig
                     (module_slug, enabled, interval_minutes, max_backups,
                      last_run_at, updated_at)
                     VALUES (%s, %s, %s, %s, now(), now())
                     ON CONFLICT (module_slug) DO UPDATE
                     SET enabled = EXCLUDED.enabled,
                         interval_minutes = EXCLUDED.interval_minutes,
                         max_backups = EXCLUDED.max_backups""",
                  [slug, enabled, minutter, behold])


def _sjekk_backupplan(c):
    """Oversettelsen, og at ingen rad ble borte eller endret oppførsel."""
    c.execute("""SELECT slug, modus, intervall_verdi, intervall_enhet,
                        behold, folger_standard
                 FROM core_backupplan ORDER BY slug""")
    rader = {r[0]: r[1:] for r in c.fetchall()}

    # Standardplanen skal være opprettet — uten den har «følger standarden»
    # ingenting å følge, og hver ny modul ville fått en plan uten mal.
    assert 'standard' in rader, f'standardplanen mangler: {sorted(rader)}'

    # **Eksisterende rader skal beholde oppførselen sin.** Arver de standarden
    # ved oppgraderingen, endrer vi hvor ofte prod tar backup uten at noen ba
    # om det — og det ville vist seg som en fil som ikke kom.
    for slug in ('patients', 'arkiv', 'oppdrag', 'oppdrag_arkiv', 'vaktliste',
                 'dogn'):
        assert slug in rader, f'{slug} forsvant i migrasjonen: {sorted(rader)}'
        assert rader[slug][4] is False, f'{slug} arver standarden uten å ha bedt om det'

    # Modus: `enabled=False` og `interval_minutes=0` er to måter å si «av».
    assert rader['patients'][0] == 'ved_endring', rader['patients']
    assert rader['oppdrag'][0] == 'av', rader['oppdrag']
    assert rader['oppdrag_arkiv'][0] == 'av', rader['oppdrag_arkiv']

    # Enheten er den groveste som gjengir minuttallet nøyaktig.
    assert rader['patients'][1:3] == (1, 'time'), rader['patients']
    assert rader['arkiv'][1:3] == (6, 'time'), rader['arkiv']
    assert rader['vaktliste'][1:3] == (45, 'minutt'), rader['vaktliste']
    assert rader['dogn'][1:3] == (1, 'dogn'), rader['dogn']

    # En rad som står av må likevel bære et intervall, ellers har feltet
    # ingen verdi å vise den dagen noen skrur den på igjen.
    assert rader['oppdrag_arkiv'][1] >= 1, rader['oppdrag_arkiv']

    # `behold` er en omdøping, ikke en ny kolonne — verdiene skal stå igjen.
    assert rader['arkiv'][3] == 20, rader['arkiv']
    assert rader['dogn'][3] == 7, rader['dogn']

    # Og de gamle kolonnene skal være borte (steg 3 av 3).
    c.execute("""SELECT column_name FROM information_schema.columns
                 WHERE table_name = 'core_backupplan'""")
    kolonner = {r[0] for r in c.fetchall()}
    assert 'enabled' not in kolonner, kolonner
    assert 'interval_minutes' not in kolonner, kolonner


#: Registeret. Nøkkelen er «app.migrasjonsnavn», som i `MigrationLoader`.
PROVER: dict[str, Migrasjonsprove] = {
    p.migrasjon: p for p in (
        Migrasjonsprove(
            migrasjon='vaktliste.0007_ressursgrupper_og_roller_per_gruppe',
            foregaaende='0006_gi_rollen_riktig_navn',
            beskrivelse='Ressursgrupper seedes, rollene viftes ut per gruppe',
            seed=_seed_0007,
            sjekk=_sjekk_0007,
        ),
        Migrasjonsprove(
            migrasjon='core.0009_backupplan_data',
            foregaaende='0007_offsitekopi',
            beskrivelse='ModuleBackupConfig blir Backupplan, med rader i basen',
            seed=_seed_backupplan,
            sjekk=_sjekk_backupplan,
        ),
        Migrasjonsprove(
            migrasjon='oppdrag.0011_fyll_oppdragsenhet',
            foregaaende='0010_flere_enheter',
            beskrivelse='Én koblingsrad per oppdrag, meldingene pekes på den',
            seed=_seed_oppdrag_0011,
            sjekk=_sjekk_oppdrag_0011,
        ),
    )
}
