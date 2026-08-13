"""Les og skriv AppSetting-verdier fra kommandolinjen.

Erstatter den ene tingen `/django-admin/` kunne som portalen ikke dekket:
å korrigere en driftsverdi manuelt. `PUT /api/settings/` skriver kun
``event_name``, og resten av nøklene — ``active_year``, ``next_patient_nr``,
``session_timeout_hours``, feature-flagg — hadde ingen annen vei inn.

Dette er bevisst en nødoperasjon og ikke en UI-flate. Verdiene endres sjelden,
og de som finnes har konsekvenser: ``active_year`` styrer hvilket år nye
pasienter havner i, og ``next_patient_nr`` styrer nummerserien. En feiltasting
i et webskjema midt i en vakt er en verre feilmodus enn at man må ha
railway-tilgang for å gjøre endringen.

Bruk::

    python manage.py appsetting --list
    python manage.py appsetting --get active_year
    python manage.py appsetting --set active_year 2027
    python manage.py appsetting --delete feature.gammelt_flagg
"""
from django.core.management.base import BaseCommand, CommandError

from patients.models import AppSetting


class Command(BaseCommand):
    help = 'Vis eller endre AppSetting-verdier (nødoperasjon, se docstring).'

    def add_arguments(self, parser):
        gruppe = parser.add_mutually_exclusive_group(required=True)
        gruppe.add_argument(
            '--list', action='store_true',
            help='Vis alle nøkler og verdier.',
        )
        gruppe.add_argument(
            '--get', metavar='NØKKEL',
            help='Vis verdien for én nøkkel.',
        )
        gruppe.add_argument(
            '--set', nargs=2, metavar=('NØKKEL', 'VERDI'),
            help='Sett verdien for én nøkkel (oppretter den om den mangler).',
        )
        gruppe.add_argument(
            '--delete', metavar='NØKKEL',
            help='Slett en nøkkel.',
        )

    def handle(self, *args, **options):
        if options['list']:
            return self._list()
        if options['get']:
            return self._get(options['get'])
        if options['set']:
            return self._set(*options['set'])
        if options['delete']:
            return self._delete(options['delete'])

    def _list(self):
        rader = AppSetting.objects.order_by('key')
        if not rader:
            self.stdout.write('Ingen innstillinger lagret.')
            return
        bredde = max(len(r.key) for r in rader)
        for rad in rader:
            self.stdout.write(f'{rad.key.ljust(bredde)}  =  {rad.value}')

    def _get(self, key):
        try:
            rad = AppSetting.objects.get(key=key)
        except AppSetting.DoesNotExist:
            raise CommandError(f'Nøkkelen «{key}» finnes ikke.')
        self.stdout.write(rad.value)

    def _set(self, key, value):
        rad = AppSetting.objects.filter(key=key).first()
        gammel = rad.value if rad else None

        AppSetting.objects.update_or_create(key=key, defaults={'value': value})

        if gammel is None:
            self.stdout.write(self.style.SUCCESS(f'Opprettet {key} = {value}'))
        elif gammel == value:
            self.stdout.write(f'{key} var allerede {value} — ingen endring.')
        else:
            self.stdout.write(self.style.SUCCESS(f'{key}: {gammel} → {value}'))

    def _delete(self, key):
        slettet, _ = AppSetting.objects.filter(key=key).delete()
        if not slettet:
            raise CommandError(f'Nøkkelen «{key}» finnes ikke.')
        self.stdout.write(self.style.SUCCESS(f'Slettet {key}.'))
