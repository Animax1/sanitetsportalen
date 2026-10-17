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


# ── core.0018 (Vaktportal, er_aktiv blir fasit) ──────────────────────────────

def _seed_vaktportal(c):
    """Den inkonsistensen prod kan ha: pekeren og flagget er uenige.

    Tre vakter. To står med `er_aktiv=True` — en taper fra et gammelt kappløp,
    og en som ble lagt inn med standardverdien — mens pekeren viser til den
    tredje, som har `er_aktiv=False`. Det er pekeren portalen registrerte på,
    så den skal vinne. I en tom base finner 0018 ingen av dem, og går grønt
    uten å ha gjort noe.
    """
    ider = {}
    for navn, aktiv in (('Taperen', True), ('Pekt paa', False), ('Standardverdi', True)):
        c.execute("""INSERT INTO core_vakt (navn, year, startet, er_aktiv)
                     VALUES (%s, 2026, now(), %s) RETURNING id""", [navn, aktiv])
        ider[navn] = c.fetchone()[0]
    c.execute("""INSERT INTO patients_appsetting (key, value)
                 VALUES ('aktiv_vakt_id', %s)
                 ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
              [str(ider['Pekt paa'])])


def _sjekk_vaktportal(c):
    c.execute("SELECT id, slug FROM core_vaktportal")
    portaler = c.fetchall()
    assert [r[1] for r in portaler] == ['standard'], portaler
    standard = portaler[0][0]

    c.execute("SELECT navn, er_aktiv, portal_id FROM core_vakt ORDER BY navn")
    vakter = {r[0]: r[1:] for r in c.fetchall()}
    assert all(portal == standard for _, portal in vakter.values()), vakter
    # Pekeren vant, og bare den er aktiv.
    assert vakter['Pekt paa'][0] is True, vakter
    assert vakter['Taperen'][0] is False, vakter
    assert vakter['Standardverdi'][0] is False, vakter

    # Indeksen fra 0019 står — og avviser en vakt til som påstår å være aktiv.
    c.execute("""SELECT indexdef FROM pg_indexes
                 WHERE indexname = 'en_aktiv_vakt_per_portal'""")
    rad = c.fetchone()
    assert rad and 'WHERE er_aktiv' in rad[0], rad


# ── accounts.0019 (medlemskap i «Standard») ──────────────────────────────────

def _seed_portaltilgang(c):
    """Fem kontoer, én for hver regel i migrasjonen.

    I en tom base finner 0019 ingen kontoer, og går grønt uten å ha gjort noe.
    """
    def konto(navn, rolle, aktiv=True):
        c.execute("""INSERT INTO accounts_customuser
                     (password, is_superuser, username, fullt_navn, er_delt_konto, role,
                      is_active, is_staff, must_change_password, mfa_required,
                      failed_login_attempts, created_at, updated_at)
                     VALUES ('!', false, %s, '', false, %s, %s, false, false, false, 0,
                             now(), now()) RETURNING id""", [navn, rolle, aktiv])
        return c.fetchone()[0]

    def rad(bruker, modul):
        c.execute("""INSERT INTO accounts_modultilgang
                     (bruker_id, modul_slug, nivaa, created_at, updated_at)
                     VALUES (%s, %s, 'les', now(), now())""", [bruker, modul])

    med = konto('med_rader', 'bruker')
    rad(med, 'patients')
    rad(med, 'oppdrag')
    konto('uten_rader', 'bruker')
    admin_med = konto('admin_med_rad', 'admin')
    rad(admin_med, 'ko')
    konto('admin_uten', 'admin')
    konto('inaktiv', 'bruker', aktiv=False)


def _sjekk_portaltilgang(c):
    c.execute("""SELECT u.username, p.slug, t.rolle
                 FROM accounts_portaltilgang t
                 JOIN accounts_customuser u ON u.id = t.bruker_id
                 JOIN core_vaktportal p ON p.id = t.portal_id ORDER BY u.username""")
    medlem = {r[0]: r[1:] for r in c.fetchall()}
    assert medlem.get('med_rader') == ('standard', 'medlem'), medlem
    assert medlem.get('uten_rader') == ('standard', 'medlem'), 'en konto uten rader ble foreldreløs'
    assert medlem.get('admin_med_rad') == ('standard', 'medlem'), 'adminens rader må høre til noe'
    assert 'admin_uten' not in medlem, 'global admin trenger ikke medlemskap'
    assert 'inaktiv' not in medlem, medlem
    assert not any(r[1] == 'moderator' for r in medlem.values()), 'ingen blir moderator av seg selv'

    c.execute("SELECT count(*) FROM accounts_modultilgang WHERE portaltilgang_id IS NULL")
    assert c.fetchone()[0] == 0, 'modulrader uten medlemskap'
    c.execute("""SELECT count(*) FROM accounts_modultilgang m
                 JOIN accounts_portaltilgang t ON t.id = m.portaltilgang_id
                 WHERE t.bruker_id <> m.bruker_id""")
    assert c.fetchone()[0] == 0, 'en modulrad hang på en annen kontos medlemskap'


def _ny_konto(c, navn, rolle='bruker', aktiv=True):
    """En konto med de kolonnene tabellen faktisk har på dette punktet i historien.

    Prøvebasen settes til én apps forrige migrasjon, og de andre appene står der
    avhengighetene drar dem — ikke nødvendigvis på dagens skjema. En `INSERT` med
    dagens kolonneliste feiler da på seg selv, ikke på migrasjonen.
    """
    c.execute("""SELECT column_name, data_type, is_nullable, column_default
                 FROM information_schema.columns WHERE table_name = 'accounts_customuser'""")
    kolonner_i_basen = c.fetchall()
    verdier = {'password': '!', 'username': navn, 'role': rolle, 'is_active': aktiv}
    noytral = {'boolean': False, 'integer': 0, 'bigint': 0, 'smallint': 0}
    # Påkrevde kolonner uten standardverdi — også de som er borte i dag, som
    # `kan_redigere_*` — får en nøytral verdi etter typen.
    for kolonne, type_, nullbar, standard in kolonner_i_basen:
        if (kolonne not in verdier and kolonne not in ('id', 'created_at', 'updated_at')
                and nullbar == 'NO' and standard is None):
            verdier[kolonne] = noytral.get(type_, '')
    kolonner = list(verdier) + ['created_at', 'updated_at']
    c.execute(f"""INSERT INTO accounts_customuser ({', '.join(kolonner)})
                  VALUES ({', '.join(['%s'] * (len(kolonner) - 2))}, now(), now())
                  RETURNING id""", [verdier[k] for k in kolonner[:-2]])
    return c.fetchone()[0]


# ── vaktliste.0031 (korpsene i «Standard», kontoenes tilhørighet) ─────────────

def _seed_tilhorighet(c):
    """To korps, en konto som fører ett av dem, og en mannskapsrad med konto i det andre."""
    def korps(navn):
        c.execute("""INSERT INTO vaktliste_korps (navn, kortnavn, er_aktiv, created_at, updated_at)
                     VALUES (%s, '', true, now(), now()) RETURNING id""", [navn])
        return c.fetchone()[0]

    def konto(navn):
        return _ny_konto(c, navn)

    hgsd, sola = korps('HGSD'), korps('Sola')
    forer, mannskap = konto('forer'), konto('mannskap')
    c.execute("""INSERT INTO vaktliste_kontokorps (user_id, korps_id, created_at, updated_at)
                 VALUES (%s, %s, now(), now())""", [forer, hgsd])
    c.execute("""INSERT INTO vaktliste_mannskap
                 (navn, korps_id, user_id, telefon, epost, epost_fra_leder, issi, er_aktiv,
                  notat, created_at, updated_at)
                 VALUES ('Kari', %s, %s, '', '', true, '', true, '', now(), now())""",
              [sola, mannskap])
    konto('uten')   # verken kontokorps eller mannskap — skal ikke få noe


def _sjekk_tilhorighet(c):
    c.execute("""SELECT k.navn, k.type FROM core_vaktportal_tilhorigheter t
                 JOIN core_vaktportal p ON p.id = t.vaktportal_id
                 JOIN vaktliste_korps k ON k.id = t.tilhorighet_id
                 WHERE p.slug = 'standard' ORDER BY k.navn""")
    assert c.fetchall() == [('HGSD', 'korps'), ('Sola', 'korps')], 'korpsene mangler i Standard'
    c.execute("""SELECT u.username, k.navn FROM core_kontotilhorighet t
                 JOIN accounts_customuser u ON u.id = t.bruker_id
                 JOIN vaktliste_korps k ON k.id = t.tilhorighet_id ORDER BY u.username""")
    assert c.fetchall() == [('forer', 'HGSD'), ('mannskap', 'Sola')], 'kontoene fikk feil tilhørighet'


# ── vaktliste.0033 (mannskapet i «Standard») ──────────────────────────────────

def _seed_mannskap_portal(c):
    c.execute("""INSERT INTO vaktliste_korps (navn, kortnavn, er_aktiv, type, created_at, updated_at)
                 VALUES ('HGSD', '', true, 'korps', now(), now()) RETURNING id""")
    korps = c.fetchone()[0]
    konto = _ny_konto(c, 'kari')
    for navn, bruker in (('Kari', konto), ('Uten konto', None)):
        c.execute("""INSERT INTO vaktliste_mannskap
                     (navn, korps_id, user_id, telefon, epost, epost_fra_leder, issi,
                      er_aktiv, notat, created_at, updated_at)
                     VALUES (%s, %s, %s, '', '', true, '', true, '', now(), now())""",
                  [navn, korps, bruker])
    c.execute("""INSERT INTO vaktliste_kontokorps (user_id, korps_id, created_at, updated_at)
                 VALUES (%s, %s, now(), now())""", [konto, korps])


def _sjekk_mannskap_portal(c):
    c.execute("SELECT id FROM core_vaktportal WHERE slug = 'standard'")
    standard = c.fetchone()[0]
    for tabell in ('vaktliste_mannskap', 'vaktliste_kontokorps'):
        c.execute(f"SELECT count(*), count(*) FILTER (WHERE portal_id = %s) FROM {tabell}",
                  [standard])
        alle, i_standard = c.fetchone()
        assert alle and alle == i_standard, f'{tabell}: {i_standard} av {alle} i Standard'


# ── patients.0021 og oppdrag.0037 (hjelperne og lokasjonene i «Standard») ─────
# Rene dataskritt, uten skjema etter — prøvene finnes fordi en tom base ikke har
# noen rader å flytte, og ville gått grønt om `filter(portal__isnull=True)` bommet.

def _seed_hjelperne_portal(c):
    konto = _ny_konto(c, 'ola')
    c.execute("""INSERT INTO patients_forstehjelper (name, user_id, is_active, created_at)
                 VALUES ('Ola', %s, true, now()), ('Uten konto', NULL, false, now())""",
              [konto])
    c.execute("""INSERT INTO patients_helsepersonell (name, user_id, is_active, created_at)
                 VALUES ('Lege 1', NULL, true, now())""")


def _sjekk_hjelperne_portal(c):
    c.execute("SELECT id FROM core_vaktportal WHERE slug = 'standard'")
    standard = c.fetchone()[0]
    for tabell in ('patients_forstehjelper', 'patients_helsepersonell'):
        c.execute(f"SELECT count(*), count(*) FILTER (WHERE portal_id = %s) FROM {tabell}",
                  [standard])
        alle, i_standard = c.fetchone()
        assert alle and alle == i_standard, f'{tabell}: {i_standard} av {alle} i Standard'


def _seed_lokasjon_portal(c):
    c.execute("""INSERT INTO oppdrag_lokasjon (navn, er_aktiv, rekkefolge, created_at, updated_at)
                 VALUES ('Scene 1', true, 0, now(), now()), ('Gammel', false, 1, now(), now())""")


def _sjekk_lokasjon_portal(c):
    c.execute("SELECT id FROM core_vaktportal WHERE slug = 'standard'")
    standard = c.fetchone()[0]
    c.execute("""SELECT count(*), count(*) FILTER (WHERE portal_id = %s)
                 FROM oppdrag_lokasjon""", [standard])
    alle, i_standard = c.fetchone()
    assert alle >= 2 and alle == i_standard, f'{i_standard} av {alle} i Standard'


# ── ko.0026 og park.0006 (KOs lister, ansvarsmerket og parklenkene i «Standard») ─

def _seed_ko_portal(c):
    for tabell in ('ko_konserttype', 'ko_kjennetegn'):
        c.execute(f"""INSERT INTO {tabell} (navn, er_aktiv, rekkefolge)
                      VALUES ('Fra før', true, 10)""")
    konto = _ny_konto(c, 'kari')
    c.execute("""INSERT INTO ko_ansvarsmerke (bruker_id, omraade, satt_at)
                 VALUES (%s, 'samband', now())""", [konto])


def _sjekk_ko_portal(c):
    c.execute("SELECT id FROM core_vaktportal WHERE slug = 'standard'")
    standard = c.fetchone()[0]
    # `ko_ansvarsomraade` har de fire `ko/0007` seedet, de andre radene over.
    for tabell in ('ko_ansvarsomraade', 'ko_konserttype', 'ko_kjennetegn', 'ko_ansvarsmerke'):
        c.execute(f"SELECT count(*), count(*) FILTER (WHERE portal_id = %s) FROM {tabell}",
                  [standard])
        alle, i_standard = c.fetchone()
        assert alle and alle == i_standard, f'{tabell}: {i_standard} av {alle} i Standard'


def _seed_parklenke_portal(c):
    c.execute("""INSERT INTO park_parklenke
                 (navn, hemmelighet_hash, aapen_fra, aapen_til, opprettet_at,
                  opprettet_av_navn, fjernet_av_navn)
                 VALUES ('Tiltakskort', repeat('a', 64), now(), now() + interval '1 day',
                         now(), '', '')""")


def _sjekk_parklenke_portal(c):
    c.execute("SELECT id FROM core_vaktportal WHERE slug = 'standard'")
    standard = c.fetchone()[0]
    c.execute("SELECT count(*), count(*) FILTER (WHERE portal_id = %s) FROM park_parklenke",
              [standard])
    alle, i_standard = c.fetchone()
    assert alle == 1 and i_standard == 1, f'{i_standard} av {alle} i Standard'


# ── core.0024 (modulene i hver portal) ───────────────────────────────────────

def _seed_portalmoduler(c):
    """To portaler, og ingen portalmoduler — `post_migrate` har alt fylt
    tabellen etter forrige `migrate`, så radene tas ut: det er migrasjonen som
    prøves, ikke kroken."""
    c.execute("DELETE FROM core_portalmodul")
    c.execute("""INSERT INTO core_vaktportal (navn, slug, er_aktiv, opprettet_at)
                 VALUES ('Brann', 'brann', true, now())""")


def _sjekk_portalmoduler(c):
    c.execute("SELECT count(*) FROM core_modulesettings")
    moduler = c.fetchone()[0]
    c.execute("SELECT count(*) FROM core_vaktportal")
    portaler = c.fetchone()[0]
    c.execute("SELECT count(*), count(DISTINCT tak) FROM core_portalmodul")
    rader, tak = c.fetchone()
    assert moduler and portaler == 2, (moduler, portaler)
    assert rader == moduler * portaler, f'{rader} rader, ventet {moduler} × {portaler}'
    c.execute("SELECT DISTINCT tak FROM core_portalmodul")
    assert [r[0] for r in c.fetchall()] == ['skriv_leder']


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
            migrasjon='core.0018_vaktportal_standard',
            foregaaende='0017_vaktportal',
            beskrivelse='Vaktene får portalen «Standard», og pekeren blir er_aktiv',
            seed=_seed_vaktportal,
            sjekk=_sjekk_vaktportal,
        ),
        Migrasjonsprove(
            migrasjon='accounts.0019_portaltilgang_standard',
            foregaaende='0018_portaltilgang',
            beskrivelse='Hver konto blir medlem av «Standard», radene kobles til medlemskapet',
            seed=_seed_portaltilgang,
            sjekk=_sjekk_portaltilgang,
        ),
        Migrasjonsprove(
            migrasjon='vaktliste.0031_tilhorighet_data',
            foregaaende='0030_korps_er_tilhorighet',
            beskrivelse='Korpsene blir med i «Standard», kontoene får tilhørigheten sin',
            seed=_seed_tilhorighet,
            sjekk=_sjekk_tilhorighet,
        ),
        Migrasjonsprove(
            migrasjon='vaktliste.0033_mannskap_i_standard',
            foregaaende='0032_mannskap_per_portal',
            beskrivelse='Mannskapet og kontoenes korps går til «Standard»',
            seed=_seed_mannskap_portal,
            sjekk=_sjekk_mannskap_portal,
        ),
        Migrasjonsprove(
            migrasjon='patients.0021_hjelperne_i_standard',
            foregaaende='0020_hjelperne_per_portal',
            beskrivelse='Førstehjelperne og helsepersonellet går til «Standard»',
            seed=_seed_hjelperne_portal,
            sjekk=_sjekk_hjelperne_portal,
        ),
        Migrasjonsprove(
            migrasjon='oppdrag.0037_lokasjoner_i_standard',
            foregaaende='0036_lokasjon_per_portal',
            beskrivelse='Lokasjonene går til «Standard»',
            seed=_seed_lokasjon_portal,
            sjekk=_sjekk_lokasjon_portal,
        ),
        Migrasjonsprove(
            migrasjon='ko.0026_ko_listene_i_standard',
            foregaaende='0025_ko_listene_per_portal',
            beskrivelse='KOs lister og ansvarsmerkene går til «Standard»',
            seed=_seed_ko_portal,
            sjekk=_sjekk_ko_portal,
        ),
        Migrasjonsprove(
            migrasjon='park.0006_parklenker_i_standard',
            foregaaende='0005_parklenke_portal',
            beskrivelse='Parklenkene går til «Standard»',
            seed=_seed_parklenke_portal,
            sjekk=_sjekk_parklenke_portal,
        ),
        Migrasjonsprove(
            migrasjon='core.0024_portalens_moduler',
            foregaaende='0023_portalmodul',
            beskrivelse='Hver portal får alle modulene, med taket på toppen',
            seed=_seed_portalmoduler,
            sjekk=_sjekk_portalmoduler,
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
