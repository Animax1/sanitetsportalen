"""Det dokumentene peker på, skal finnes (14. sep. 2026).

**Hvorfor dette er en test.** Dokumentasjon har ingen testsuite, og det viste seg i
dokumentrunden: `docs/DEPLOY_GUIDE.md` forklarte hvordan man **laster ned** en backupfil
for å kontrollere at den ikke inneholder passord-hasher. Begge deler var feil — den hele
databasebackupen inneholder dem med vilje, og det finnes ingen nedlastingsfunksjon. Hadde
noen fulgt oppskriften, hadde de lagt en helseopplysningsdump i nedlastingsmappa mens de
trodde de gjorde en sikkerhetskontroll.

`README.md` og `docs/PERSONVERN_DOKUMENTASJON.md` beskrev i tillegg rollemodellen
`read_only`/`read_write`/`lead_view`/`lead`, som ble slettet i deploy 2. Det er ikke en
foreldet beskrivelse av dagens mekanisme — det er en beskrivelse av en *annen* mekanisme.

**Denne testen fanger ikke slikt.** Den kan ikke lese mening, og en påstand som er feil
på innholdet går rett gjennom. Det den fanger er den mekaniske halvdelen: at en filsti,
en `manage.py`-kommando eller et kodesymbol dokumentene navngir, fortsatt finnes. Det er
den halvdelen som råtner av seg selv, uten at noen gjør noe galt — en fil flytter, og
seks dokumenter blir stille feil.

Den er altså et gulv, ikke et tak. Innholdet må fortsatt leses av et menneske.

**Fire mutasjoner prøvd, tre fanget:** en død filsti, en `manage.py`-kommando som ikke
finnes, og et slettet symbol påstått som gjeldende.

**Den fjerde slapp gjennom, og det står her framfor å skjules:** skriver man
`> **Historisk**` over en påstand, tier regelen om alt til neste kapittel. Markøren er en
bevisst luke — historiske avsnitt *skal* kunne nevne slettede navn — men den er lett å
misbruke, og den skiller ikke mellom «dette avsnittet beskriver fortida» og «jeg vil at
denne testen skal være stille». Det er samme avveining som enhver unntaksliste i
prosjektet, og den løses av at noen leser diffen, ikke av at testen blir strengere.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROT = Path(settings.BASE_DIR)

#: Dokumentene som holdes ved like. `docs/archived/` er med vilje utenfor —
#: arkiverte dokumenter skal beskrive tilstanden da de ble skrevet.
DOKUMENTER = [
    'README.md',
    'CLAUDE.md',
    # Modulfilene (15. sep. 2026). De **må** stå her: da CLAUDE.md ble delt,
    # flyttet nær halvparten av stiene, kommandoene og symbolene ut av fila
    # denne testen leste — og delingen ville i stillhet ha slått av regelen
    # for nettopp den dokumentasjonen som råtner fortest, den som beskriver
    # én modul. `core/tests_claude_md.py` håndhever at nye modulfiler kommer
    # med hit.
    'patients/CLAUDE.md',
    'oppdrag/CLAUDE.md',
    'vaktliste/CLAUDE.md',
    'statistikk/CLAUDE.md',
    'ko/CLAUDE.md',
    'backlog/CLAUDE.md',
    'docs/DEPLOY_GUIDE.md',
    'docs/RUNBOOK_VAKT.md',
    'docs/TEKNISK_DOKUMENTASJON.md',
    'docs/PERSONVERN_DOKUMENTASJON.md',
    'docs/BACKUP.md',
]

#: Stier som med vilje nevnes selv om de ikke finnes — historiske referanser.
#: Unntaksliste med begrunnelse, ikke en tillatelse.
STIER_UNNTATT = {
    # Monolitten som ble delt i mai 2026 og slettet 13. aug. 2026. Nevnes i
    # teksten nettopp for å forklare at referanser til den er historiske.
    'static/js/script.js',
}

#: Kommandoer Django selv leverer, som ikke ligger i prosjektets egne mapper.
DJANGO_KOMMANDOER = {
    'migrate', 'makemigrations', 'showmigrations', 'collectstatic',
    'createcachetable', 'createsuperuser', 'runserver', 'test', 'shell',
    'check', 'dumpdata', 'loaddata', 'flush',
}


def _les(navn: str) -> str:
    return (ROT / navn).read_text(encoding='utf-8')


def _egne_kommandoer() -> set[str]:
    return {p.stem for p in ROT.glob('*/management/commands/*.py') if p.stem != '__init__'}


def _finnes(sti: str) -> bool:
    """Stier oppgis dels fra rota, dels relativt til `templates/`."""
    return (ROT / sti).exists() or (ROT / 'templates' / sti).exists()


#: Ord som gjør et treff til en historisk forklaring i stedet for en påstand.
#: En slettet fil *skal* kunne nevnes i setningen som forteller at den er borte.
FORKLARER = (
    'slettet', 'fjernet', 'erstattet', 'borte', 'finnes ikke', 'historisk',
    'tidligere', 'var ', 'sto ', 'gammel', 'legacy', 'avviklet', 'ikke lenger',
    'død kode', 'overtatt', 'utgått', 'flyttet',
)

#: Hvor mange linjer rundt treffet som regnes som samme avsnitt.
#:
#: Prosa brytes over flere linjer, og forklaringen står ofte på linja etter
#: navnet. Med en ren linjesjekk meldte testen fem falske funn i setninger som
#: *sa* at navnet var slettet — bare med ordet på neste linje.
KONTEKST = 3


#: Et avsnitt kan erklære seg historisk **én gang, øverst**, og da gjelder det
#: til neste overskrift. Det er slik en leser faktisk leser: markøren står i
#: ingressen, ikke på hver linje. Uten dette meldte testen fem funn inne i
#: tillegg som alt var merket «Historisk (mai 2026)» i første setning.
SEKSJONSMARKØRER = ('> **historisk', '*ikke gjennomgått', '> *ikke gjennomgått',
                    '**levert', '*levert')


def _historiske_linjer(linjer: list[str]) -> set[int]:
    """Indeksene som ligger under en seksjon merket historisk."""
    ut, i_historisk = set(), False
    for i, linje in enumerate(linjer):
        lav = linje.lstrip().lower()
        # Nullstilles på **kapittelnivå** (`## `), ikke på enhver overskrift:
        # et `### `-underavsnitt inne i et historisk tillegg er fortsatt
        # historisk. Med `startswith('#')` slapp `### Scheduler` ut av
        # markeringen og meldte et falskt funn.
        if linje.startswith('## ') or linje.startswith('# '):
            i_historisk = False
        elif any(lav.startswith(m) for m in SEKSJONSMARKØRER):
            i_historisk = True
        if i_historisk:
            ut.add(i)
    return ut


def _forklares(linjer: list[str], i: int, historiske: set[int] | None = None) -> bool:
    """Står det i nærheten — eller i seksjonens ingress — at navnet er borte?"""
    if historiske is not None and i in historiske:
        return True
    fra = max(0, i - KONTEKST)
    til = min(len(linjer), i + KONTEKST + 1)
    vindu = ' '.join(linjer[fra:til]).lower()
    return any(ord_ in vindu for ord_ in FORKLARER)


class DokumenteneFinnesTests(SimpleTestCase):

    def test_alle_dokumentene_i_lista_finnes(self):
        """Sperrehake: forsvinner et dokument, skal testen si fra her og ikke
        stille slutte å måle det."""
        mangler = [d for d in DOKUMENTER if not (ROT / d).exists()]
        self.assertEqual(mangler, [], f'dokumenter i lista finnes ikke: {mangler}')


class FilstierTests(SimpleTestCase):
    """Hver `sti/til/fil.py` i backticks skal finnes."""

    #: To mønstre, og det andre finnes fordi det første ikke var nok.
    #:
    #: `patients/middleware._MetricsStore` sto i en tabellcelle **uten**
    #: backticks og gikk rett forbi da modulen flyttet til `core`. Stier uten
    #: backticks er like døde som stier med.
    MØNSTER = re.compile(r'`([a-z_][a-z_0-9]*/[a-z_0-9./-]*\.(?:py|js|md|html|toml|json|in|txt))`')
    MØNSTER_NAKEN = re.compile(r'(?<![`\w/])([a-z_][a-z_0-9]*(?:/[a-z_0-9-]+)+\.(?:py|js))\b')

    def test_hver_filsti_finnes(self):
        feil = []
        for dok in DOKUMENTER:
            linjer = _les(dok).splitlines()
            historiske = _historiske_linjer(linjer)
            for i, linje in enumerate(linjer):
                funn = set(self.MØNSTER.findall(linje)) | set(self.MØNSTER_NAKEN.findall(linje))
                for sti in funn:
                    if sti in STIER_UNNTATT or _finnes(sti):
                        continue
                    # En slettet fil kan nevnes i setningen som sier at den er
                    # slettet — det er ofte nettopp det man trenger å vite.
                    if _forklares(linjer, i, historiske):
                        continue
                    feil.append(f'{dok}:{i + 1}: {sti}')
        self.assertEqual(
            feil, [],
            'Disse filstiene finnes ikke lenger:\n  ' + '\n  '.join(feil)
            + '\n\nFlytt referansen, eller før stien opp i STIER_UNNTATT med begrunnelse.')

    def test_vi_finner_faktisk_stier(self):
        """Uten denne kan mønsteret slutte å treffe, og testen over går grønn
        mens den måler ingenting."""
        antall = sum(len(set(self.MØNSTER.findall(_les(d)))) for d in DOKUMENTER)
        self.assertGreater(antall, 50, f'fant bare {antall} filstier — mønsteret treffer feil')

    def test_ogsaa_stier_uten_backticks(self):
        """Sperrehake for det andre mønsteret, som lett kan slutte å treffe."""
        antall = sum(len(set(self.MØNSTER_NAKEN.findall(_les(d)))) for d in DOKUMENTER)
        self.assertGreater(antall, 5, f'fant bare {antall} nakne stier')


class KommandoerTests(SimpleTestCase):
    """Hver `manage.py <navn>` skal være en kommando som finnes."""

    MØNSTER = re.compile(r'manage\.py ([a-z_]+)')

    def test_hver_kommando_finnes(self):
        egne = _egne_kommandoer()
        feil = []
        for dok in DOKUMENTER:
            for navn in sorted(set(self.MØNSTER.findall(_les(dok)))):
                if navn in egne or navn in DJANGO_KOMMANDOER:
                    continue
                feil.append(f'{dok}: manage.py {navn}')
        self.assertEqual(
            feil, [],
            'Disse kommandoene finnes ikke:\n  ' + '\n  '.join(feil))

    def test_vi_finner_faktisk_kommandoer(self):
        antall = sum(len(set(self.MØNSTER.findall(_les(d)))) for d in DOKUMENTER)
        self.assertGreater(antall, 10, f'fant bare {antall} kommandoer')


class TallpaastanderTests(SimpleTestCase):
    """Tall i dokumentene skal stemme med tall regnet ut fra koden.

    **Dette er den ene klassen som fanger noe annet enn døde navn.** De øvrige
    reglene her ser at en filsti eller en kommando fortsatt finnes; denne ser
    at en *påstand* fortsatt er sann.

    Den finnes fordi dokumentrunden 14. sep. 2026 fant to påstander av nettopp
    denne sorten, og ingen av dem var noens feil: «178 tester totalt» var sant
    da det ble skrevet, og «16 endepunkter» var sant den gangen det var alt som
    fantes. Tall råtner av seg selv.

    **Påstandene registreres eksplisitt, ikke gjettes ut av prosaen.** Et
    mønster som lette etter «<tall> endepunkter» hvor som helst ville truffet
    setninger som ikke er påstander om totalen, og en test med falske funn blir
    slått av. Hver rad her er et bevisst valg om at *dette* tallet skal holdes
    i live.

    **Grensen er verdt å vite:** dette fanger tall, ikke mening. At kapittel 5
    dokumenterte 16 av 123 endepunkter fanges nå; at de 16 hadde feil
    tilgangskrav gjør det ikke. Se klassens naboer og modulens docstring.
    """

    #: (dokument, regex med én gruppe, nøkkel i `fasit()`, hva raden gjelder)
    #:
    #: Regexen skal treffe **nøyaktig ett** sted. Treffer den flere, sier
    #: testen fra — da er påstanden enten duplisert eller mønsteret for løst.
    PAASTANDER = [
        ('docs/TEKNISK_DOKUMENTASJON.md', r'Portalen har \*\*(\d+) endepunkter\*\*',
         'ruter_totalt', 'totalt antall ruter'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'\| `/pasienter/` \| (\d+) \|',
         'ruter_pasienter', 'ruter under /pasienter/'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'\| `/oppdrag/` \| (\d+) \|',
         'ruter_oppdrag', 'ruter under /oppdrag/'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'\| `/vaktliste/` \| (\d+) \|',
         'ruter_vaktliste', 'ruter under /vaktliste/'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'\| `/portal-admin/` \| (\d+) \|',
         'ruter_portal-admin', 'ruter under /portal-admin/'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'\| `/accounts/` \| (\d+) \|',
         'ruter_accounts', 'ruter under /accounts/'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'\| `/statistikk/` \| (\d+) \|',
         'ruter_statistikk', 'ruter under /statistikk/'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'\| `/ko/` \| (\d+) \|',
         'ruter_ko', 'ruter under /ko/'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'\| `/backlog/` \| (\d+) \|',
         'ruter_backlog', 'ruter under /backlog/'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'(\d+) ruter, alle i `core/urls_admin\.py`',
         'ruter_portal-admin', 'ruter i adminflaten'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'(\d+) filer i `static/js/`',
         'js_filer', 'JS-filer'),
        ('docs/TEKNISK_DOKUMENTASJON.md', r'(\w+) handlere i registeret:',
         'backup_handlere', 'backup-handlere'),
        ('CLAUDE.md', r'(\w+) handlere i dag:',
         'backup_handlere', 'backup-handlere'),
        ('README.md', r'\*\*To lag\.\*\* (\w+) handlere:',
         'backup_handlere', 'backup-handlere'),
        ('docs/DEPLOY_GUIDE.md', r'\| \*\*Modulfiler\*\* \| (\w+) handlere',
         'backup_handlere', 'backup-handlere'),
    ]

    def test_hver_registrert_paastand_stemmer(self):
        from core.tallfasit import fasit, som_tall

        f = fasit()
        feil = []
        for dok, moenster, noekkel, hva in self.PAASTANDER:
            tekst = _les(dok)
            treff = re.findall(moenster, tekst)
            if not treff:
                feil.append(f'{dok}: fant ikke påstanden om {hva} '
                            f'(mønster: {moenster}) — er den omformulert eller borte?')
                continue
            if len(treff) > 1:
                feil.append(f'{dok}: påstanden om {hva} treffer {len(treff)} steder — '
                            f'enten duplisert, eller mønsteret er for løst')
                continue
            paastaatt = som_tall(treff[0])
            if paastaatt is None:
                feil.append(f'{dok}: «{treff[0]}» er ikke et tall jeg kjenner '
                            f'({hva}) — legg det i TALLORD')
            elif paastaatt != f[noekkel]:
                feil.append(f'{dok}: {hva} står som {treff[0]!r}, men koden har '
                            f'{f[noekkel]}')
        self.assertEqual(
            feil, [],
            'Tall i dokumentene stemmer ikke med koden:\n  ' + '\n  '.join(feil)
            + '\n\nKjør `python manage.py tallfasit` for å se de riktige tallene.')

    def test_fasiten_gir_tall_som_gir_mening(self):
        """Sperrehake mot testen over.

        Regner `fasit()` feil — for eksempel null ruter fordi URL-oppslaget
        endret form — ville testen over feilet på *alle* rader og blitt lest
        som «dokumentene er gale». Denne sier i stedet at fasiten er gal.
        """
        from core.tallfasit import fasit

        f = fasit()
        self.assertGreater(f['ruter_totalt'], 50, 'fant nesten ingen ruter')
        self.assertGreater(f['backup_handlere'], 3, 'fant nesten ingen handlere')
        self.assertGreater(f['js_filer'], 10, 'fant nesten ingen JS-filer')
        self.assertEqual(
            f['backup_handlere'], f['backup_modulfiler'] + 1,
            'modulfilene pluss den hele skal være alle handlerne')
        self.assertEqual(
            f['ruter_totalt'],
            sum(v for k, v in f.items() if k.startswith('ruter_') and k != 'ruter_totalt'),
            'summen av prefiksene skal være totalen — ellers faller ruter mellom')


class SlettedeSymbolerTests(SimpleTestCase):
    """Navn som er fjernet fra koden skal ikke stå som om de finnes.

    Dette er den ene regelen som fanger *innhold* og ikke bare stier, og den
    finnes fordi nettopp disse navnene sto i fire dokumenter etter at de var
    slettet. Lista utvides når noe fjernes — det er billigere enn å oppdage
    det i neste dokumentrunde.

    Et navn får stå i en setning som forklarer at det er borte. Regelen er
    derfor at treffet må ha et av ordene under i nærheten.
    """

    #: (symbol, hvor det ble av)
    SLETTET = [
        ('BACKUP_APPS', 'aldri erstattet — backup styres av registeret'),
        ('RETENTION_HOURS', 'erstattet av core.Backupplan.behold'),
        ('BackupConfig', 'erstattet av core.Backupplan'),
        ('ModuleBackupConfig', 'erstattet av core.Backupplan'),
        ('has_role_at_least', 'fjernet i deploy 2'),
        ('kan_redigere_pasienter', 'fjernet i deploy 3'),
        ('lead_view', 'rollen finnes ikke etter deploy 2'),
    ]

    def test_slettede_navn_staar_bare_i_forklaringer(self):
        feil = []
        for dok in DOKUMENTER:
            linjer = _les(dok).splitlines()
            historiske = _historiske_linjer(linjer)
            for i, linje in enumerate(linjer):
                lav = linje.lower()
                for symbol, _ in self.SLETTET:
                    if symbol.lower() not in lav:
                        continue
                    if _forklares(linjer, i, historiske):
                        continue
                    feil.append(f'{dok}:{i + 1}: {symbol} — {linje.strip()[:90]}')
        self.assertEqual(
            feil, [],
            'Disse linjene nevner noe som er slettet, uten å si at det er slettet:\n  '
            + '\n  '.join(feil)
            + '\n\nEnten fjern referansen, eller skriv om den slik at det står at '
              'navnet er borte.')
