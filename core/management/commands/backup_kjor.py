"""Kjør backup for de planene som er forfalt — manuell inngang til klokka.

    python manage.py backup_kjor              # kjør det som er forfalt
    python manage.py backup_kjor --alle       # kjør alle planer nå, uansett
    python manage.py backup_kjor --modul oppdrag
    python manage.py backup_kjor --status     # skriv planene og gå

**Dette er ikke en cron-jobb.** Klokka er en tråd i web-prosessen, fordi
Railway-volumet bare kan henge på én tjeneste og det er web-tjenesten som har
det — se `core/backup/klokke.py` for hva en cron-tjeneste uten volum ville
gjort. Kommandoen finnes for å kjøre en runde for hånd:

    railway ssh --service web -- python manage.py backup_kjor --alle

typisk rett før en risikofylt deploy, eller for å se at oppsettet virker.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.kommando import lesbar_dbfeil


class Command(BaseCommand):
    help = 'Kjør automatisk backup for planene som er forfalt.'

    def add_arguments(self, parser):
        parser.add_argument('--alle', action='store_true',
                            help='Kjør alle planer nå, også de som ikke er forfalt.')
        parser.add_argument('--modul', help='Bare denne modulen (slug).')
        parser.add_argument('--status', action='store_true',
                            help='Skriv ut planene og avslutt uten å kjøre noe.')

    def handle(self, *args, **valg):
        # Én lesbar linje hvis databasen ikke svarer, i stedet for fire
        # stablede tracebacks. En backup som ikke ble tatt blir savnet den
        # dagen man trenger den, ikke den dagen den feilet.
        with lesbar_dbfeil('ingen backup ble tatt'):
            self._kjor(valg)

    def _kjor(self, valg):
        from core.backup import get_handler
        from core.backup.klokke import forfalt, kjor_plan, planer, vakthund

        par = planer()
        if not par:
            self.stdout.write('Ingen registrerte backup-handlere.')
            return

        if valg['status']:
            self._skriv_status(par, vakthund())
            return

        if valg['modul']:
            if get_handler(valg['modul']) is None:
                raise CommandError(
                    f'Ingen backup-handler for «{valg["modul"]}». '
                    f'Kjente: {", ".join(slug for slug, _ in par)}')
            par = [(slug, plan) for slug, plan in par if slug == valg['modul']]

        skrevet = hoppet = 0
        for slug, plan in par:
            if not valg['alle'] and not forfalt(plan):
                continue
            if kjor_plan(slug, tving=valg['alle']):
                skrevet += 1
                self.stdout.write(self.style.SUCCESS(f'  {slug}: ny fil'))
            else:
                hoppet += 1
                self.stdout.write(f'  {slug}: ingen ny fil (uendret, av, eller låst)')

        if not skrevet and not hoppet:
            self.stdout.write('Ingenting var forfalt.')
            return
        self.stdout.write(self.style.SUCCESS(
            f'Ferdig: {skrevet} ny(e) fil(er), {hoppet} uten.'))

    def _skriv_status(self, par, overdue):
        na = timezone.now()
        overdue_slugger = {r['slug'] for r in overdue}
        self.stdout.write(f'{"Modul":<16}{"Modus":<13}{"Intervall":<28}'
                          f'{"Behold":<8}{"Siste fil":<14}Sist vurdert')
        for slug, plan in par:
            g = plan.gjeldende()
            arv = ' (standard)' if plan.arver else ''
            fil = (plan.sist_fil_at.strftime('%d.%m %H:%M')
                   if plan.sist_fil_at else '—')
            if plan.sist_sjekket_at:
                alder = int((na - plan.sist_sjekket_at).total_seconds() // 60)
                sjekk = f'for {alder} min siden'
            else:
                sjekk = 'aldri'
            linje = (f'{slug:<16}{g.get_modus_display():<13}'
                     f'{g.intervall_tekst() + arv:<28}{g.behold:<8}{fil:<14}{sjekk}')
            if slug in overdue_slugger:
                self.stdout.write(self.style.WARNING(linje + '  ← forsinket'))
            else:
                self.stdout.write(linje)
        if overdue:
            self.stdout.write(self.style.WARNING(
                '\nEn eller flere planer er ikke vurdert på tre ganger '
                'intervallet. Står web-tjenesten, har klokketråden stoppet.'))
