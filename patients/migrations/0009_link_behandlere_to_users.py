"""Fase 5: Auto-koble Behandler/Helsepersonell til CustomUser via navn.

Brukeren har bevisst satt ``Behandler.name`` og ``Helsepersonell.name`` lik
``CustomUser.username``. Denne migrasjonen utfører case-insensitive matching
og kobler 1:1 der det finnes treff.

Sikkerhet:
- Migrasjonen feiler IKKE ved manglende treff — den logger antall koblet
  og antall uten treff via print() (synlig i ``manage.py migrate``-output).
- ``OneToOneField`` betyr at hvis to Behandler-rader ville pekt på samme
  bruker, hopper vi over duplikatet og varsler. Skjer ikke i praksis siden
  navn er ``unique=True`` på Behandler.
- Reverse-migrasjon (``migrate patients 0008``) nuller ut user-feltene
  igjen slik at vi kan rulle tilbake trygt.
"""
from django.db import migrations


def link_users_by_name(apps, schema_editor):
    Behandler = apps.get_model('patients', 'Behandler')
    Helsepersonell = apps.get_model('patients', 'Helsepersonell')
    User = apps.get_model('accounts', 'CustomUser')

    linked_b = 0
    linked_h = 0
    missing_b = []
    missing_h = []
    conflict_b = 0
    conflict_h = 0

    # ── Behandlere ──
    for b in Behandler.objects.filter(user__isnull=True):
        user = User.objects.filter(username__iexact=b.name).first()
        if user is None:
            missing_b.append(b.name)
            continue
        # OneToOne: sjekk at brukeren ikke allerede er koblet til en annen Behandler
        if Behandler.objects.filter(user=user).exists():
            conflict_b += 1
            continue
        b.user = user
        b.save(update_fields=['user'])
        linked_b += 1

    # ── Helsepersonell ──
    for h in Helsepersonell.objects.filter(user__isnull=True):
        user = User.objects.filter(username__iexact=h.name).first()
        if user is None:
            missing_h.append(h.name)
            continue
        if Helsepersonell.objects.filter(user=user).exists():
            conflict_h += 1
            continue
        h.user = user
        h.save(update_fields=['user'])
        linked_h += 1

    # Logg resultatet til migrate-output
    print(f'  → Koblet {linked_b} Behandler-rad(er) til CustomUser.')
    print(f'  → Koblet {linked_h} Helsepersonell-rad(er) til CustomUser.')
    if missing_b:
        print(f'  → {len(missing_b)} Behandler-rad(er) uten matchende bruker: '
              f'{", ".join(missing_b[:10])}{"..." if len(missing_b) > 10 else ""}')
    if missing_h:
        print(f'  → {len(missing_h)} Helsepersonell-rad(er) uten matchende bruker: '
              f'{", ".join(missing_h[:10])}{"..." if len(missing_h) > 10 else ""}')
    if conflict_b or conflict_h:
        print(f'  → {conflict_b + conflict_h} rad(er) hoppet over pga. konflikt '
              '(bruker allerede koblet).')


def unlink_all_users(apps, schema_editor):
    Behandler = apps.get_model('patients', 'Behandler')
    Helsepersonell = apps.get_model('patients', 'Helsepersonell')
    Behandler.objects.update(user=None)
    Helsepersonell.objects.update(user=None)


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0008_behandler_user_helsepersonell_user'),
        ('accounts', '0007_module_permission_flags'),
    ]

    operations = [
        migrations.RunPython(link_users_by_name, reverse_code=unlink_all_users),
    ]
