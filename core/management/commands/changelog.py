"""Slå opp i CHANGELOG uten å lese den.

    python manage.py changelog                      # alle 281 titlene
    python manage.py changelog --temaer             # vokabularet
    python manage.py changelog --tema vaktliste/roller
    python manage.py changelog --app vaktliste
    python manage.py changelog --umerkede           # entries uten søkeord
"""
from django.core.management.base import BaseCommand

from core import changelog


class Command(BaseCommand):
    help = 'Titler og søkeord i CHANGELOG. Se core/changelog.py.'

    def add_arguments(self, parser):
        parser.add_argument('--tema', help='Ett søkeord, f.eks. vaktliste/roller')
        parser.add_argument('--app', help='Alt merket med denne modulen')
        parser.add_argument('--temaer', action='store_true', help='Vis vokabularet')
        parser.add_argument('--umerkede', action='store_true',
                            help='Entries uten søkeord — halen som gjenstår')

    def handle(self, *args, **o):
        if o['temaer']:
            i_bruk = changelog.sokeord_i_bruk()
            for app, temaer in sorted(changelog.TEMAER.items()):
                self.stdout.write(f'\n  {app}')
                for tema, hva in sorted(temaer.items()):
                    n = len(changelog.finn(f'{app}/{tema}'))
                    merke = ' ' if n else '·'   # · = registrert, ikke brukt ennå
                    self.stdout.write(f'    {merke} {tema:16} {n:3}  {hva}')
            self.stdout.write('')
            return

        if o['umerkede']:
            rader = [e for e in changelog.entries() if not e['sokeord']]
            alle = len(changelog.entries())
            for e in rader:
                self.stdout.write(f"  {e['dato']}  {e['tittel'][:84]}")
            self.stdout.write(f'\n  {len(rader)} av {alle} entries er uten søkeord.')
            return

        rader = changelog.finn(sokeord=o['tema'], app=o['app'])
        for e in rader:
            merker = '  '.join(f'#{s}' for s in e['sokeord'])
            self.stdout.write(f"  {e['dato']}  {e['tittel'][:76]}")
            if merker:
                self.stdout.write(f"  {'':12}{merker}")
        self.stdout.write(f'\n  {len(rader)} entries.')
