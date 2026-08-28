"""Deploy 2 (§8): `role` krymper fra fem verdier til `admin` og `bruker`.

Rekkefølgen i deploy-planen er selve sikkerheten. Deploy 1 la til
``ModulTilgang``, fylte tabellen fra `role` og slo på håndhevelsen — men lot
`role` stå urørt, slik at en rollback hadde fasiten i behold. Først når
koden ikke lenger leser de fire tilgangsverdiene noe sted, kan feltet krympe.

**Hva som forsvinner, og hva som ikke gjør det.** Verdiene `lead`,
`lead_view`, `read_write` og `read_only` blir til `bruker`. Tilgangen de
beskrev ligger allerede i ``ModulTilgang``-rader fra migrasjon 0012, og de
radene røres ikke her. Det som faktisk går tapt er *etiketten* — at en konto
en gang het «Leder». Var den forskjellen verdt å beholde, måtte den vært
lagret som noe annet enn tilgangskontroll.

**Etter denne migrasjonen er `ModulTilgang` eneste fasit.** En rollback av
deploy 1 kan ikke lenger gjenskape matrisen fra `role`, fordi `role` ikke
lenger vet hvem som hadde skrivetilgang. Det er derfor deploy 2 er et eget
steg, og ikke slått sammen med deploy 1.
"""
from django.db import migrations, models


#: Gammel verdi → ny verdi. `admin` står ikke her: den overlever uendret,
#: og er den eneste verdien noe i koden faktisk gater på.
KRYMPING = {
    'lead': 'bruker',
    'lead_view': 'bruker',
    'read_write': 'bruker',
    'read_only': 'bruker',
}


def krymp(apps, schema_editor):
    """Skriv de fire tilgangsverdiene om til `bruker`.

    Alt som ikke er `admin` eller en av de fire kjente verdiene får `bruker`
    også. En ukjent verdi i kolonnen er data vi ikke kan tolke, og den
    tryggeste tolkningen er den uten privilegier — `admin` deles ikke ut av
    en migrasjon.
    """
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.exclude(role='admin').update(role='bruker')


def utvid(apps, schema_editor):
    """Reversering: `bruker` → `read_only`.

    Den laveste av de gamle verdiene, med vilje. Reverseringen kan ikke vite
    hvem som var `lead` eller `read_write`, og en gjetning oppover ville delt
    ut tilgang ingen har bestemt. `ModulTilgang` er uansett fasit for hva
    kontoene faktisk får lov til — denne verdien er kun en etikett etter
    rollbacken.
    """
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.exclude(role='admin').update(role='read_only')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_fyll_modultilgang'),
    ]

    operations = [
        migrations.RunPython(krymp, utvid),
        # `choices` er ikke et databaseattributt (Django: `Field.non_db_attrs`).
        # På PostgreSQL — altså prod — sammenligner skjemaredigereren type,
        # null, unique og index, og finner ingen forskjell: ingen SQL kjøres.
        # SQLite bygger tabellen om uansett, fordi den mangler ALTER for det
        # meste; det gjelder bare lokalt og i offline-modus.
        #
        # Operasjonen står her for at migrasjonsstaten skal stemme med
        # modellen — uten den ville `makemigrations` lage en ny, tom
        # migrasjon ved neste kjøring.
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[('admin', 'Administrator'), ('bruker', 'Bruker')],
                default='bruker', max_length=20, verbose_name='Rolle',
            ),
        ),
    ]
