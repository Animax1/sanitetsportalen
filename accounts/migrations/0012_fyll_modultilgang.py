"""Fyll ``ModulTilgang`` fra ``role``, og fra ``role`` alene.

**Flagget ignoreres med vilje.** De fem ``kan_redigere_*``-flaggene styrer i
dag kun dashboard og nav-meny; de har aldri stengt et endepunkt (§2.1 i
docs/BESLUTNING_ROLLEMODELLEN.md). Utledet vi fra flagget, ville brukere som i
dag *kan* nå modulen via URL-en mistet den i det håndhevelsen slås på — og en
migrasjon som stille trekker tilbake tilgang oppdager du midt i en vakt.

Alle beholder altså nøyaktig den tilgangen de faktisk har i dag. Radene som
oppstår for brukere uten flagget bekrefter en tilgang de allerede hadde; ingen
privilegier oppstår, de blir bare synlige. Innstrammingen gjøres etterpå, for
hånd, i matrisen — synlig og reversibel.

Kartleggingen er §8.1:

    read_only   → patients: les
    read_write  → patients: skriv_full
    lead_view   → patients: les        + statistikk: les
    lead        → patients: skriv_full + statistikk: les
    admin       → ingen rader (global admin)

``lead`` og ``lead_view`` sin eneste forskjell fra rollene under er
statistikk, og den bevares som en egen rad. Kartleggingen er derfor tapsfri
etter *rettigheter*. «Leder» som betegnelse bevares bevisst ikke — se §3.1.
"""
from django.db import migrations


# Kartleggingen ligger som data, ikke som if-er, slik at den kan leses opp mot
# tabellen i §8.1 uten å spore gjennom kontrollflyt.
KARTLEGGING = {
    'read_only':  [('patients', 'les')],
    'read_write': [('patients', 'skriv_full')],
    'lead_view':  [('patients', 'les'),        ('statistikk', 'les')],
    'lead':       [('patients', 'skriv_full'), ('statistikk', 'les')],
    'admin':      [],
}


def fyll(apps, schema_editor):
    CustomUser = apps.get_model('accounts', 'CustomUser')
    ModulTilgang = apps.get_model('accounts', 'ModulTilgang')

    rader = []
    for bruker in CustomUser.objects.all().iterator():
        for slug, nivaa in KARTLEGGING.get(bruker.role, []):
            rader.append(ModulTilgang(
                bruker_id=bruker.pk, modul_slug=slug, nivaa=nivaa,
            ))

    # ignore_conflicts gjør migrasjonen trygg å kjøre om igjen — f.eks. etter
    # en rollback og ny fram. Uten den ville unique-constraint-en stoppet
    # deployen på andre forsøk.
    ModulTilgang.objects.bulk_create(rader, ignore_conflicts=True)


def tom(apps, schema_editor):
    """Reversering tømmer tabellen.

    Trygt fordi deploy 1 lar ``role`` og de fem flaggene stå urørt: fasiten
    finnes fortsatt, og en ny fram-migrering bygger radene på nytt. Det er
    nettopp derfor deploy 1 og deploy 3 ikke kan slås sammen — fjernes
    flaggene i samme deploy, har en rollback ingenting å bygge fra.
    """
    apps.get_model('accounts', 'ModulTilgang').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_modultilgang'),
    ]

    operations = [
        migrations.RunPython(fyll, tom),
    ]
