"""Synkroniser `is_superuser` med `PermissionsMixin` i Django 5.2. Ingen SQL.

Migrasjonshistorikken (`0001_initial`) har feltet som::

    models.BooleanField(default=False, verbose_name='superuser status')

Django 5.2 sin `PermissionsMixin` legger i tillegg på `help_text`. **Det er hele
forskjellen** — samme type, samme default, samme verbose_name.

`help_text` står i Djangos `Field.non_db_attrs`, så `_field_should_be_altered()`
returnerer False og `alter_field()` returnerer før den rører databasen. Det
gjelder uansett backend, ikke bare Postgres. Verifisert med `sqlmigrate`, som
skriver `-- (no-op)`.

**Hvorfor den ikke ble kjørt i august:** den var med i den genererte utgaven av
`0008`, og ble strippet derfra fordi en annen kosmetisk migrasjon
(`audit/0004`, en indeks-omdøping) crash-loopet release-fasen samme dag. Det
var riktig forsiktighet under en hendelse, men de to var ikke i samme klasse:
indeks-omdøpingen beskrev en fortid som ikke hadde skjedd, mens denne ikke
beskriver databasen i det hele tatt.

Å la den ligge ukjørt hadde en pris. `makemigrations` foreslo den ved hver
kjøring, og forslaget fikk nummer `0009` — samme nummer som neste ekte
migrasjon. Den som kjørte `makemigrations accounts && git add -A` uten å lese
resultatet, ville fått den med på lasset i en helt annen leveranse.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_customuser_current_session_key_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='is_superuser',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Designates that this user has all permissions without '
                    'explicitly assigning them.'
                ),
                verbose_name='superuser status',
            ),
        ),
    ]
