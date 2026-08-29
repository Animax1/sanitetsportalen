"""Backfill: én Vakt per år som finnes, og pasientradene pekt dit.

Deploy 1 av `docs/BESLUTNING_VAKT_SOM_SCOPE.md`. Additiv og rullbar: `year`
står urørt på radene og er fortsatt det all lesing bruker.

**Navnet blir årstallet, ikke `event_name`.** `event_name` er én global verdi
som beskriver vakten som var aktiv da noen sist skrev den — ikke nødvendigvis
den som eide radene fra 2026. Å fryse dagens verdi inn på en historisk vakt
ville påstått noe vi ikke vet. Årstallet er sant, og kan endres for hånd
etterpå av den som vet hva vakten het.

`startet`/`avsluttet` for historiske vakter er estimater fra radenes
tidsstempler — eldste og nyeste rad det året. Redigerbare, som navnet.

Oppdragsradene tas i `oppdrag.0006`, som kjører etter denne: oppdrag avhenger
av patients i kode, og migrasjonsgrafen følger samme retning.
"""
from datetime import datetime

from django.db import migrations
from django.utils import timezone


def _aktivt_aar(AppSetting):
    rad = AppSetting.objects.filter(key='active_year').first()
    try:
        return int(rad.value) if rad else None
    except (TypeError, ValueError):
        return None


def _lag_vakt(Vakt, year, aktivt, forste, siste):
    er_aktiv = (year == aktivt)
    return Vakt.objects.create(
        navn=str(year),
        year=year,
        startet=forste or timezone.make_aware(datetime(year, 1, 1)),
        # En historisk vakt er over. Nyeste rad det året er et estimat på
        # når — ærligere enn NULL, som ville sagt «pågår fortsatt».
        avsluttet=None if er_aktiv else siste,
        er_aktiv=er_aktiv,
    )


def backfill(apps, schema_editor):
    Vakt = apps.get_model('core', 'Vakt')
    Patient = apps.get_model('patients', 'Patient')
    VaktArkiv = apps.get_model('patients', 'VaktArkiv')
    AppSetting = apps.get_model('patients', 'AppSetting')

    aktivt = _aktivt_aar(AppSetting)

    aar = (set(Patient.objects.values_list('year', flat=True).distinct())
           | set(VaktArkiv.objects.values_list('year_snapshot', flat=True)
                 .distinct()))

    for year in sorted(aar):
        pasienter = Patient.objects.filter(year=year).order_by('created_at')
        forste = getattr(pasienter.first(), 'created_at', None)
        siste = getattr(pasienter.last(), 'created_at', None)
        if forste is None:
            # Året finnes kun som arkiv. Arkiveringstidspunktet er det
            # nærmeste vi kommer.
            arkiv = (VaktArkiv.objects.filter(year_snapshot=year)
                     .order_by('importert_at').first())
            forste = siste = getattr(arkiv, 'importert_at', None)

        vakt = _lag_vakt(Vakt, year, aktivt, forste, siste)
        Patient.objects.filter(year=year).update(vakt=vakt)
        VaktArkiv.objects.filter(year_snapshot=year).update(vakt=vakt)

    if aktivt is not None:
        vakt = Vakt.objects.filter(year=aktivt).first()
        if vakt is not None:
            AppSetting.objects.update_or_create(
                key='aktiv_vakt_id', defaults={'value': str(vakt.pk)})
    # Finnes ingen rader (fersk installasjon), lages ingen vakt her:
    # `hent_aktiv_vakt()` oppretter lat ved første behov, samme mønster som
    # `get_active_year` gjør med sin AppSetting-rad.


def reverser(apps, schema_editor):
    """Rollback av deploy 1: `year` er fortsatt fasit, så vaktene kan gå.

    FK-ene må nulles før vaktene slettes — `PROTECT` nekter ellers, også i en
    reversering. Oppdragsradene er alt nullet av `oppdrag.0006`, som
    reverseres før denne.
    """
    Vakt = apps.get_model('core', 'Vakt')
    Patient = apps.get_model('patients', 'Patient')
    VaktArkiv = apps.get_model('patients', 'VaktArkiv')
    AppSetting = apps.get_model('patients', 'AppSetting')

    Patient.objects.update(vakt=None)
    VaktArkiv.objects.update(vakt=None)
    Vakt.objects.all().delete()
    AppSetting.objects.filter(key='aktiv_vakt_id').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0014_patient_vakt_vaktarkiv_vakt'),
    ]

    operations = [
        migrations.RunPython(backfill, reverser),
    ]
