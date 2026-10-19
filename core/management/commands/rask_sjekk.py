"""Testene for det du har endret, raskt — `core/rask_sjekk.py` velger dem.

    python manage.py rask_sjekk                  # mot HEAD: det som ikke er committet
    python manage.py rask_sjekk --mot staging    # alt på grenen siden staging
    python manage.py rask_sjekk --vis            # bare si hva som ville kjørt
    python manage.py rask_sjekk --med-treg       # ta med testene merket «treg»

Ikke et alternativ til hele suiten før push, og ikke til CI. Se CLAUDE.md.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.rask_sjekk import TREG, apper_med_tester, velg


def endrede_filer(mot: str, rot: Path) -> list[str]:
    """Endret mot `mot` (committet eller ikke), pluss nye filer git ikke kjenner."""
    def git(*arg):
        res = subprocess.run(['git', *arg], cwd=rot, capture_output=True, text=True)
        if res.returncode != 0:
            raise CommandError(f'git {" ".join(arg)} feilet: {res.stderr.strip()}')
        return [linje for linje in res.stdout.splitlines() if linje.strip()]
    return sorted(set(git('diff', '--name-only', mot))
                  | set(git('ls-files', '--others', '--exclude-standard')))


def testkommando(etiketter: list[str], *, med_treg: bool, parallel: str) -> list[str]:
    """`manage.py test …` med testbasen beholdt.

    **En underprosess, ikke `call_command('test')`:** `settings.py` slår på den
    raske passordhasheren og broene som kaster under test bare når
    `sys.argv[1] == 'test'`. Kjørt herfra ville testene møtt PBKDF2 og prod-broene.
    """
    kommando = [sys.executable, 'manage.py', 'test', *etiketter,
                '--keepdb', '--noinput', '-v', '1', '--parallel', parallel]
    if not med_treg:
        kommando += ['--exclude-tag', TREG]
    return kommando


class Command(BaseCommand):
    help = 'Kjør testene for appene du har endret, med testbasen beholdt.'

    def add_arguments(self, parser):
        parser.add_argument('--mot', default='HEAD',
                            help='Sammenlign med denne refen (standard: HEAD).')
        parser.add_argument('--vis', action='store_true',
                            help='Skriv ut kommandoen uten å kjøre den.')
        parser.add_argument('--med-treg', action='store_true',
                            help=f'Ta med testene merket «{TREG}».')
        parser.add_argument('--parallel', default='auto',
                            help='Antall prosesser (standard: auto).')

    def handle(self, *args, **valg):
        rot = Path(settings.BASE_DIR)
        filer = endrede_filer(valg['mot'], rot)
        if not filer:
            self.stdout.write(f'Ingen endringer mot {valg["mot"]}.')
            return
        utvalg = velg(filer, rot)
        if utvalg.etiketter is None:
            self.stdout.write(f'Hele suiten — {utvalg.grunner[0]}.')
            etiketter = sorted(apper_med_tester(rot))
        else:
            for grunn in utvalg.grunner:
                self.stdout.write(f'  {grunn}')
            self.stdout.write('De tverrgående skannerne i core er ikke med; '
                              'de tas av hele suiten før push.')
            etiketter = utvalg.etiketter
        kommando = testkommando(etiketter, med_treg=valg['med_treg'],
                                parallel=valg['parallel'])
        self.stdout.write(' '.join(kommando[1:]))
        if valg['vis']:
            return
        res = subprocess.run(kommando, cwd=rot)
        if res.returncode != 0:
            raise CommandError('Testene feilet.', returncode=res.returncode)
