"""Skriv `scripts/sikkerhetsruter.json` på nytt fra `urlpatterns`. Se `core/sikkerhetsruter.py`."""
from django.core.management.base import BaseCommand

from core import sikkerhetsruter


class Command(BaseCommand):
    help = 'Skriv rutene sikkerhetssjekken prøver, fra urlpatterns.'

    def handle(self, *args, **opts):
        data = sikkerhetsruter.bygg()
        sikkerhetsruter.FIL.write_text(sikkerhetsruter.som_tekst(data), encoding='utf-8')
        self.stdout.write(f"{len(data['stengt'])} stengt, {len(data['aapne'])} åpne, "
                          f"{len(data['omdirigerer'])} omdirigerer → {sikkerhetsruter.FIL}")
