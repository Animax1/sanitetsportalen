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
    )
}
