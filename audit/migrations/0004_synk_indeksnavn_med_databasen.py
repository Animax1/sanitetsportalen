"""Rett Djangos tilstand for `created_at`-indeksen. Rører ikke databasen.

**Bakgrunn, verifisert mot produksjon 23. aug. 2026** (`pg_indexes` og
`django_migrations` lest direkte):

| | Navn |
|---|---|
| Prod-databasen | `audit_audit_created_2c1626_idx` |
| Djangos migrasjonstilstand etter `0002` | `audit_audit_created_a3c1b8_idx` |
| Modellen (`Index(fields=['created_at'])`) | `audit_audit_created_2c1626_idx` |

Databasen og modellen er altså enige. Det er kun den registrerte tilstanden som
avviker, og det er derfor `makemigrations` har foreslått en omdøping ved hver
kjøring siden Django 5-oppgraderingen.

`a3c1b8` er ikke et navn Django genererer for denne indeksen — verken for
`['created_at']` (`2c1626`) eller `['-created_at']` (`6e540c`). De to andre
navnene `0002` satte er derimot eksakt riktige. `0002` skrev altså ett navn
som aldri har hatt dekning i modellen.

**Hvorfor den forrige `0004` tok ned produksjon 13. august 2026:** den ble
generert som en ekte `RenameIndex` og forsøkte
`ALTER INDEX audit_audit_created_a3c1b8_idx RENAME TO ...`. Den indeksen fantes
ikke — databasen sto allerede på målnavnet. Release-fasen kjører `migrate`, så
en migrasjon som ikke kan kjøre crash-looper containeren. Migrasjonen var ikke
farlig fordi den gjorde noe drastisk; den var umulig fordi den beskrev en
fortid som ikke hadde skjedd. Den fila ble fjernet, og `django_migrations` har
ingen `0004`-rad for `audit` — navnet her er derfor ledig og bevisst et annet.

**Derfor: kun tilstand, ingen SQL.** `database_operations` er tom med vilje.
Det som skal rettes er Djangos bokføring, ikke databasen, og release-fasen er
det siste stedet man vil ha en betinget kodesti.

**Kjent skjevhet, akseptert:** en database bygget fra migrasjonene fra bunnen
får fortsatt indeksen hetende `a3c1b8` fra `0002`, mens tilstanden nå sier
`2c1626`. Det gjelder lokale utviklingsbaser og testdatabasen, som begge er
kortlevde og aldri sjekker indeksnavn. Alternativet — betinget SQL i
release-fasen — er en større risiko enn skjevheten den fjerner. Prod er
fasiten, og etter denne migrasjonen stemmer tilstanden med prod.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0003_auditlog_app_label'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameIndex(
                    model_name='auditlog',
                    new_name='audit_audit_created_2c1626_idx',
                    old_name='audit_audit_created_a3c1b8_idx',
                ),
            ],
        ),
    ]
