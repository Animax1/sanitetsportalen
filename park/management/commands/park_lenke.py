"""Lag, list og fjern parklenker fra kommandolinja.

Oppsettsiden på `/lag/` er pulje 2; til da er dette veien, og etterpå er det
reserven — samme rolle som `create_admin` har for kontoene.

    python manage.py park_lenke --lag "Tiltakskort Bliksund" --fra 2026-10-01T08:00 --til 2026-10-04T08:00
    python manage.py park_lenke --list
    python manage.py park_lenke --fjern 3

**Tokenet skrives ut én gang** (`FORSLAG_PARK.md` §4.1). Står det ikke i
tiltakskortet da, lages en ny.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from park import services
from park.models import Parklenke


def _tidspunkt(raa, navn):
    t = parse_datetime(raa or '')
    if t is None:
        raise CommandError(f'--{navn} må være et tidspunkt, f.eks. 2026-10-01T08:00.')
    if timezone.is_naive(t):
        t = timezone.make_aware(t)
    return t


class Command(BaseCommand):
    help = 'Lag, list og fjern lenkene lagene registrerer med på /lag/r/.'

    def add_arguments(self, parser):
        parser.add_argument('--lag', metavar='NAVN', help='Lag en ny lenke med dette navnet.')
        parser.add_argument('--fra', help='Åpen fra (lokal tid), f.eks. 2026-10-01T08:00.')
        parser.add_argument('--til', help='Åpen til (lokal tid).')
        parser.add_argument('--list', action='store_true', help='List lenkene.')
        parser.add_argument('--fjern', type=int, metavar='ID', help='Fjern lenken med denne ID-en.')

    def handle(self, *args, **opt):
        if opt['lag']:
            try:
                lenke, token = services.lag_lenke(
                    navn=opt['lag'], aapen_fra=_tidspunkt(opt['fra'], 'fra'),
                    aapen_til=_tidspunkt(opt['til'], 'til'))
            except services.Ugyldig as feil:
                raise CommandError(str(feil)) from None
            self.stdout.write(f'Lenke {lenke.pk} «{lenke.navn}» er laget.')
            self.stdout.write('Adressen vises bare nå — legg den i tiltakskortet:')
            self.stdout.write(f'  https://<portalens domene>/lag/r/#{token}')
            return
        if opt['fjern'] is not None:
            lenke = Parklenke.objects.filter(pk=opt['fjern']).first()
            if lenke is None:
                raise CommandError(f'Ingen lenke med ID {opt["fjern"]}.')
            services.fjern_lenke(lenke)
            self.stdout.write(f'Lenke {lenke.pk} «{lenke.navn}» er fjernet.')
            return
        if opt['list']:
            for l in Parklenke.objects.all():
                status = 'fjernet' if l.fjernet_at else 'aktiv'
                self.stdout.write(
                    f'{l.pk:>4}  {l.navn}  {services.tid_tekst(l.aapen_fra)}–{services.tid_tekst(l.aapen_til)}'
                    f'  {status}  sist brukt: {services.tid_tekst(l.sist_brukt_at) if l.sist_brukt_at else "aldri"}')
            return
        raise CommandError('Oppgi --lag, --list eller --fjern.')
