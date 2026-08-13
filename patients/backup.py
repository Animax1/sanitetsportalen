"""Backup-handler for patients-modulen.

Registrerer en BaseBackupHandler-subklasse i core.backup-registry
slik at sentral backup/restore-tjeneste kan håndtere patients-data.

Bevarer dagens sikkerhetsregel: KUN pasientrelaterte data inkluderes.
Brukere, MFA-hemmeligheter og audit-spor er bevisst utelatt.
"""
from __future__ import annotations

from core.backup import BaseBackupHandler, register


class PatientsBackupHandler(BaseBackupHandler):
    """Backup-handler for pasientregistrerings-modulen.

    SIKKERHET:
    - ``apps`` inkluderer kun ``patients``-modeller — accounts, audit
      og sessions røres aldri.
    - ``exclude`` fjerner Backup og BackupConfig fra dump for å unngå
      selvreferanse (backupen som lages skal ikke være med i innholdet).
    - ``restore_models`` lister opp modellene som skal slettes før
      ``loaddata`` kjøres, i FK-trygg rekkefølge (barn først).
    """
    slug = 'patients'
    display_name = 'Pasientregistrering'

    apps = ['patients']
    exclude = [
        # Backup og BackupConfig skal ikke være med i sin egen dump.
        'patients.Backup',
        'patients.BackupConfig',
        # Arkivet håndteres av ArkivBackupHandler og skal aldri endres av en
        # pasient-restore. Begge modellene må ekskluderes: tidligere var kun
        # VaktArkiv utelatt mens ArkivertPasient ble med, altså barna uten
        # forelderen. Var arkivet slettet i mellomtiden, feilet loaddata på
        # fremmednøkkel og hele gjenopprettingen rullet tilbake.
        'patients.VaktArkiv',
        'patients.ArkivertPasient',
    ]
    restore_models = [
        # Slett-rekkefølge: barn -> foreldre. Patient har FK til Forstehjelper
        # og Helsepersonell, så Patient må slettes først.
        # Arkivmodellene er IKKE her — de røres aldri av pasient-restore.
        'patients.Patient',
        'patients.Forstehjelper',
        'patients.Helsepersonell',
        'patients.AppSetting',
    ]

    def inspect_restore_payload(self, objects):
        """Se over kliniske felt i fixturen mot whitelisten i choices.py.

        `loaddata` går utenom all applikasjonsvalidering, så dette var den
        siste veien inn i databasen der en verdi utenfor whitelisten kunne
        lande usett. API-et validerer, og `import_offline_data` fikk samme
        kontroll i N6.

        Rapporten er per felt og verdi, ikke per rad — er en backup fra før
        whitelisten ble innført, er poenget å se *hva* som avviker, ikke å få
        én linje per pasient. Verdiene forkortes: de kan i prinsippet være
        vilkårlig lang fritekst, og loggen skal fortsatt være lesbar.

        Advarslene stopper ikke gjenopprettingen — se base-klassen.
        """
        from collections import Counter

        from .choices import CHOICE_FIELDS

        avvik = Counter()
        for obj in objects:
            if not isinstance(obj, dict) or obj.get('model') != 'patients.patient':
                continue
            felter = obj.get('fields') or {}
            for felt, tillatte in CHOICE_FIELDS.items():
                verdi = felter.get(felt)
                if verdi in (None, ''):
                    continue
                if str(verdi).strip() not in tillatte:
                    avvik[(felt, str(verdi))] += 1

        advarsler = []
        for (felt, verdi), antall in sorted(avvik.items()):
            vist = verdi if len(verdi) <= 60 else verdi[:57] + '...'
            advarsler.append(
                f'gjenoppretting: {felt}={vist!r} er ikke en gyldig verdi '
                f'({antall} rad(er)). Backupen er eldre enn whitelisten, '
                f'eller dataene er endret utenfor API-et.'
            )
        return advarsler


class ArkivBackupHandler(BaseBackupHandler):
    """Backup-handler for vaktarkivet.

    Arkivet er skilt ut som egen modul fordi det har helt andre behov enn
    den aktive vaktdataen:

    - Det endres sjelden (én gang per arrangement), så det trenger ikke
      hyppig backup.
    - Det skal aldri berøres av en pasient-restore, og motsatt.
    - Railways egen databasebackup er kun aktiv den måneden abonnementet er
      oppgradert. Resten av året er dette den eneste dekningen arkivet har.

    ``apps`` peker på enkeltmodeller, ikke en app-label: modellene bor i
    ``patients``-appen, men utgjør en egen backup-enhet. ``dumpdata``
    aksepterer ``app_label.ModelName``.

    Forelder og barn hører sammen i samme dump — et arkiv uten sine
    pasientrader, eller rader uten sitt arkiv, er ikke gjenopprettbart.
    """
    slug = 'arkiv'
    display_name = 'Vaktarkiv'

    apps = ['patients.VaktArkiv', 'patients.ArkivertPasient']
    exclude = []
    restore_models = [
        # Barn først: ArkivertPasient har FK til VaktArkiv.
        'patients.ArkivertPasient',
        'patients.VaktArkiv',
    ]
    # ``importert_av`` peker på CustomUser, som ikke er med i denne dumpen.
    # Med natural_foreign lagres den som brukernavnet, og er kontoen slettet
    # feiler HELE gjenopprettingen med DeserializationError — altså akkurat
    # når man trenger backupen. Brukernavnet ligger uansett frosset i
    # ``importert_av_navn``, så FK-en utelates.
    strip_fields = {'patients.VaktArkiv': ['importert_av']}


def register_handlers() -> None:
    """Kalles fra patients.apps.PatientsConfig.ready().

    Idempotent: klargjør for at apps.ready() kan kalles flere ganger
    ved testkjøring uten å lage duplikater.
    """
    register(PatientsBackupHandler())
    register(ArkivBackupHandler())
