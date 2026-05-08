"""Innledende migrasjon for accounts-appen."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, verbose_name='superuser status')),
                ('username', models.CharField(max_length=64, unique=True, verbose_name='Brukernavn')),
                ('email', models.EmailField(blank=True, max_length=120, unique=True, verbose_name='E-post')),
                ('role', models.CharField(
                    choices=[('admin', 'Administrator'), ('read_write', 'Les/skriv'), ('read_only', 'Kun lesing')],
                    default='read_only',
                    max_length=20,
                    verbose_name='Rolle',
                )),
                ('is_active', models.BooleanField(default=True, verbose_name='Aktiv')),
                ('is_staff', models.BooleanField(default=False, verbose_name='Stab (Django Admin)')),
                ('must_change_password', models.BooleanField(default=True, verbose_name='Må endre passord')),
                ('failed_login_attempts', models.IntegerField(default=0, verbose_name='Mislykkede innloggingsforsøk')),
                ('locked_until', models.DateTimeField(blank=True, null=True, verbose_name='Låst til')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Opprettet')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Oppdatert')),
                ('last_login_at', models.DateTimeField(blank=True, null=True, verbose_name='Siste innlogging')),
                ('groups', models.ManyToManyField(
                    blank=True, related_name='customuser_set',
                    to='auth.group', verbose_name='groups',
                )),
                ('user_permissions', models.ManyToManyField(
                    blank=True, related_name='customuser_set',
                    to='auth.permission', verbose_name='user permissions',
                )),
            ],
            options={
                'verbose_name': 'Bruker',
                'verbose_name_plural': 'Brukere',
                'ordering': ['username'],
            },
        ),
        migrations.CreateModel(
            name='LoginEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username_attempt', models.CharField(max_length=64, verbose_name='Brukernavn forsøkt')),
                ('success', models.BooleanField(verbose_name='Vellykket')),
                ('ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP-adresse')),
                ('user_agent', models.TextField(blank=True, verbose_name='User-agent')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Tidspunkt')),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='login_events',
                    to='accounts.customuser',
                    verbose_name='Bruker',
                )),
            ],
            options={
                'verbose_name': 'Innloggingshendelse',
                'verbose_name_plural': 'Innloggingshendelser',
                'ordering': ['-created_at'],
            },
        ),
    ]
