"""Skriv ut tallene dokumentene får lov til å påstå."""
from django.core.management.base import BaseCommand

from core.tallfasit import fasit, ruter_per_prefiks


class Command(BaseCommand):
    help = 'Tall om portalen, regnet ut fra koden. Se core/tallfasit.py.'

    def handle(self, *args, **options):
        for navn, verdi in sorted(fasit().items()):
            self.stdout.write(f'  {navn:24} {verdi}')
        self.stdout.write('')
        self.stdout.write('  Ruter per prefiks:')
        for p, n in sorted(ruter_per_prefiks().items()):
            self.stdout.write(f'    {p:18} {n}')
