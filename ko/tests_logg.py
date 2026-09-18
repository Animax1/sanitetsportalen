"""KO-loggen: reglene, portene og sletteinngangen (pulje 2).

Tyngden ligger der `CLAUDE.md` sier den skal ligge: **tjenestelaget tungt**
(hver gren, hver grense, hver sperre), **portene på viewene**, og ingenting på
markup. En feil i `services` legger seg i data og oppdages av ingen; en feil i
malen ser den som åpner siden.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.models import AppSetting
from core.vakt import hent_aktiv_vakt
from ko import services
from ko.models import KILDE_SYSTEM, Logglinje


def _bruker(navn, **kwargs):
    return CustomUser.objects.create_user(
        username=navn, password='x', must_change_password=False, **kwargs)


def _gi_ko(bruker, nivaa):
    ModulTilgang.objects.update_or_create(
        bruker=bruker, modul_slug='ko', defaults={'nivaa': nivaa})
    return bruker


class TidspunktetTests(TestCase):
    """**Kaster, i motsetning til vaktlistas `vurder_klienttid`.**

    Der er det en offline-kø som spiller av et trykk, og en stille korreksjon
    til servertid er bedre enn en tapt stempling. Her har et menneske skrevet
    et klokkeslett, og å lagre noe annet enn det hun skrev — uten å si fra — er
    nøyaktig den stille feilen loggen finnes for å unngå.
    """

    def test_ingen_verdi_gir_naa(self):
        naa = timezone.now()
        self.assertEqual(services.vurder_tidspunkt(None, naa), naa)

    def test_tilbake_i_tid_er_lov(self):
        """Den ekte bruken: operatøren skriver 21:14 klokka 21:40."""
        naa = timezone.now()
        foer = naa - timedelta(minutes=26)
        self.assertEqual(services.vurder_tidspunkt(foer, naa), foer)

    def test_for_langt_tilbake_avvises(self):
        naa = timezone.now()
        with self.assertRaises(services.Ugyldig):
            services.vurder_tidspunkt(naa - timedelta(days=1, seconds=1), naa)

    def test_begge_grensene_selv_er_lov(self):
        """Av-med-én, **begge veier**.

        `>` → `>=` overlevde første mutasjonsrunde på begge grensene (17. sep.
        2026): prøvene rundt sto et sekund utenfor og tretti sekunder
        innenfor, så selve grensene var udekket. Bakover treffer en operatør
        som fører gårsdagens siste linje rett etter midnatt nøyaktig her;
        framover er det en nettleserklokke som går et helt minutt foran.
        """
        naa = timezone.now()
        eldst = naa - services.MAKS_ALDER
        self.assertEqual(services.vurder_tidspunkt(eldst, naa), eldst)
        ferskest = naa + services.MAKS_FRAMTID
        self.assertEqual(services.vurder_tidspunkt(ferskest, naa), ferskest)

    def test_framtid_utover_slakken_avvises(self):
        naa = timezone.now()
        with self.assertRaises(services.Ugyldig):
            services.vurder_tidspunkt(naa + timedelta(minutes=2), naa)

    def test_klokkeslingring_slipper_gjennom(self):
        """Nettleserens klokke kan gå noen sekunder foran serverens. Avvises
        det, får operatøren en feilmelding på en linje hun skrev riktig."""
        naa = timezone.now()
        litt_fram = naa + timedelta(seconds=30)
        self.assertEqual(services.vurder_tidspunkt(litt_fram, naa), litt_fram)


class TekstenTests(TestCase):

    def test_tom_avvises(self):
        for raa in ('', '   ', None):
            with self.subTest(raa=raa):
                with self.assertRaises(services.Ugyldig):
                    services.rens_tekst(raa)

    def test_for_lang_avvises(self):
        with self.assertRaises(services.Ugyldig):
            services.rens_tekst('x' * (services.MAKS_TEKST + 1))

    def test_grensa_selv_er_lov(self):
        """Av-med-én, begge veier. En grense som avviser sin egen verdi er en
        annen grense enn den som står dokumentert."""
        self.assertEqual(len(services.rens_tekst('x' * services.MAKS_TEKST)),
                         services.MAKS_TEKST)

    def test_markup_lagres_raatt(self):
        """Ingen vasking ved lagring: «BT < 90» er en lovlig linje.

        Forsvaret hører hjemme ved utskriften (`escapeHtml` i ko.js), og en
        vasking her ville ødelagt teksten uten å være et forsvar.
        """
        self.assertEqual(services.rens_tekst('BT < 90 <b>obs</b>'),
                         'BT < 90 <b>obs</b>')


class ForfatterenFrysesTests(TestCase):
    """§4.5: visningsnavn endres og kontoer slettes, og en logg der avsenderen
    forsvinner er verdiløs akkurat når den leses."""

    def setUp(self):
        self.vakt = hent_aktiv_vakt()

    def test_navnet_overlever_at_kontoen_slettes(self):
        bruker = _bruker('kari')
        linje = services.skriv_linje(self.vakt, 'noe skjedde', bruker=bruker)
        bruker.delete()
        linje.refresh_from_db()
        self.assertEqual(linje.forfatter_navn, 'kari')
        self.assertIsNone(linje.forfatter_id)

    def test_delt_konto_fryses_paa_linja(self):
        """Kontoen kan ha byttet type siden, så spørsmålet kan ikke stilles på
        nytt i ettertid. «Enhet 2» og «Kari Nordmann» betyr fundamentalt ulike
        ting, og blir loggen lest i en personalsak er den forskjellen alt."""
        bil = _bruker('enhet2', er_delt_konto=True)
        linje = services.skriv_linje(self.vakt, 'melder ledig', bruker=bil)
        bil.er_delt_konto = False
        bil.save(update_fields=['er_delt_konto'])
        linje.refresh_from_db()
        self.assertTrue(linje.forfatter_delt_konto)


class RettingTests(TestCase):
    """§4.3: **ny rad som peker på den gamle**, aldri en endring."""

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.bruker = _bruker('ola')

    def _skriv(self, tekst='første'):
        return services.skriv_linje(self.vakt, tekst, bruker=self.bruker)

    def test_den_gamle_raden_blir_staaende(self):
        linje = self._skriv()
        services.korriger(linje, bruker=self.bruker, tekst='rettet')
        linje.refresh_from_db()
        self.assertEqual(linje.tekst, 'første')
        self.assertEqual(Logglinje.objects.count(), 2)

    def test_bare_den_nyeste_gjelder(self):
        linje = self._skriv()
        services.korriger(linje, bruker=self.bruker, tekst='rettet')
        gjeldende = list(Logglinje.objects.gjeldende(self.vakt))
        self.assertEqual([l.tekst for l in gjeldende], ['rettet'])

    def test_kjedet_retting_gir_fortsatt_en_linje(self):
        linje = self._skriv()
        en = services.korriger(linje, bruker=self.bruker, tekst='andre')
        services.korriger(en, bruker=self.bruker, tekst='tredje')
        gjeldende = list(Logglinje.objects.gjeldende(self.vakt))
        self.assertEqual([l.tekst for l in gjeldende], ['tredje'])

    def test_rettet_linje_blir_staaende_paa_plassen_sin(self):
        """**Fortellingens rekkefølge, ikke `tidspunkt`** (§4.3).

        Uten `rot` ville en rettet linje hoppet til bunnen og lest som om den
        skjedde sist — og det er som fortelling loggen har verdi. Prøven er
        skrevet med tre linjer fordi feilen bare er synlig når det står noe
        *etter* den som rettes.
        """
        forste = self._skriv('en')
        self._skriv('to')
        self._skriv('tre')
        services.korriger(forste, bruker=self.bruker, tekst='en (rettet)')
        gjeldende = list(Logglinje.objects.gjeldende(self.vakt))
        self.assertEqual([l.tekst for l in gjeldende],
                         ['en (rettet)', 'to', 'tre'])

    def test_kjedet_retting_beholder_ogsaa_plassen(self):
        """Ledd tre skal arve **første** ledds plass, ikke andre ledds.

        Det er hele grunnen til at `rot` finnes ved siden av `korrigerer`: med
        bare `korrigerer` ville sorteringen fulgt forrige retting, som ligger
        nederst.
        """
        forste = self._skriv('en')
        self._skriv('to')
        en = services.korriger(forste, bruker=self.bruker, tekst='en b')
        services.korriger(en, bruker=self.bruker, tekst='en c')
        gjeldende = list(Logglinje.objects.gjeldende(self.vakt))
        self.assertEqual([l.tekst for l in gjeldende], ['en c', 'to'])

    def test_to_rettinger_av_samme_linje_avvises(self):
        linje = self._skriv()
        services.korriger(linje, bruker=self.bruker, tekst='min retting')
        with self.assertRaises(services.AlleredeKorrigert):
            services.korriger(linje, bruker=self.bruker, tekst='din retting')

    def test_uendret_avvises(self):
        """En «retting» som ikke retter noe ville lagt en rad i loggen som
        sier at noe ble rettet. Det er en løgn i et dokument."""
        linje = self._skriv()
        with self.assertRaises(services.Ugyldig):
            services.korriger(linje, bruker=self.bruker, tekst='første')

    def test_systemlinje_kan_ikke_rettes(self):
        """Den er en projeksjon av noe som skjedde i oppdragsmodulen, og
        rettes der. Gikk veien om KO, ville de to modulene sagt hver sin ting
        om samme tidspunkt."""
        linje = services.systemlinje(
            self.vakt, 'oppdrag_status', {'enhet': 'HGSD 56'})
        with self.assertRaises(services.Ugyldig):
            services.korriger(linje, bruker=self.bruker, tekst='nei')

    def test_tidspunktet_kan_rettes_uten_at_teksten_roeres(self):
        linje = self._skriv('kollaps ved scene sør')
        ny_tid = timezone.now() - timedelta(minutes=30)
        ny = services.korriger(linje, bruker=self.bruker, tidspunkt=ny_tid)
        self.assertEqual(ny.tekst, 'kollaps ved scene sør')
        self.assertEqual(ny.tidspunkt, ny_tid)

    def test_registrert_at_foelger_ikke_med_i_rettingen(self):
        """`tidspunkt` er korrigerbart, `registrert_at` er det aldri (§4.3).
        Blandes de, kan en frist flyttes ved å rette et klokkeslett."""
        linje = self._skriv()
        ny = services.korriger(
            linje, bruker=self.bruker,
            tidspunkt=timezone.now() - timedelta(hours=2))
        self.assertGreater(ny.registrert_at, linje.tidspunkt)


class SletteinngangenTests(TestCase):
    """§4.4: **tøm innholdet, la rada stå.**"""

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.bruker = _bruker('ola')
        self.leder = _bruker('andre')

    def test_teksten_tommes_og_raden_staar(self):
        linje = services.skriv_linje(self.vakt, 'Kari Hansen, 41 år',
                                     bruker=self.bruker)
        services.fjern(linje, bruker=self.leder)
        linje.refresh_from_db()
        self.assertEqual(linje.tekst, '')
        self.assertTrue(linje.er_fjernet)
        self.assertEqual(linje.fjernet_av_navn, 'andre')
        self.assertEqual(Logglinje.objects.filter(pk=linje.pk).count(), 1)

    def test_hele_kjeden_tommes(self):
        """**Den viktigste prøven i fila.**

        Rettes en linje og deretter fjernes den, ville den opprinnelige
        teksten blitt stående i den overstyrte raden — usynlig i loggen, men
        fullt lesbar i basen og i backupfila. En sletteinngang som lar en kopi
        ligge igjen, er ikke en sletteinngang.
        """
        linje = services.skriv_linje(self.vakt, 'Kari Hansen', bruker=self.bruker)
        ny = services.korriger(linje, bruker=self.bruker, tekst='kvinne, 41')
        services.fjern(ny, bruker=self.leder)
        self.assertEqual(
            list(Logglinje.objects.values_list('tekst', flat=True)), ['', ''])

    def test_fjerning_fra_roten_tommer_ogsaa_rettingen(self):
        """Samme regel fra den andre kanten: inngangen skal virke uansett
        hvilket ledd i kjeden operatøren har foran seg."""
        linje = services.skriv_linje(self.vakt, 'Kari Hansen', bruker=self.bruker)
        services.korriger(linje, bruker=self.bruker, tekst='kvinne, 41')
        services.fjern(linje, bruker=self.leder)
        self.assertEqual(
            list(Logglinje.objects.values_list('tekst', flat=True)), ['', ''])

    def test_systemlinjer_roeres_ikke(self):
        """De bærer ingen fritekst, og en inngang som nådde dem ville vært en
        vei til å fjerne sporet etter en overstyring."""
        system = services.systemlinje(
            self.vakt, 'oppdrag_status', {'enhet': 'HGSD 56'})
        services.fjern(system, bruker=self.leder)
        system.refresh_from_db()
        self.assertFalse(system.er_fjernet)


class OppbevaringstidenTests(TestCase):
    """730 dager som standard, styrt av en `AppSetting`."""

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.bruker = _bruker('ola')

    def test_standard_uten_rad(self):
        self.assertEqual(services.oppbevaringsdager(), 730)

    def test_verdien_leses(self):
        AppSetting.set(services.DAGER_NOKKEL, 90)
        self.assertEqual(services.oppbevaringsdager(), 90)

    def test_soppel_faller_tilbake_til_standard(self):
        AppSetting.set(services.DAGER_NOKKEL, 'i fjor')
        self.assertEqual(services.oppbevaringsdager(), 730)

    def test_verdien_klemmes_ved_lesing_og_ikke_bare_ved_lagring(self):
        """En verdi skrevet for hånd i shellet, eller av en eldre versjon,
        skal ikke kunne tømme loggen. Sperren hører hjemme der verdien
        *brukes*, fordi det er den veien `purge_old_logs` går."""
        AppSetting.set(services.DAGER_NOKKEL, 0)
        self.assertEqual(services.oppbevaringsdager(), services.DAGER_MIN)
        AppSetting.set(services.DAGER_NOKKEL, 99999)
        self.assertEqual(services.oppbevaringsdager(), services.DAGER_MAKS)

    def test_gamle_linjer_slettes(self):
        gammel = services.skriv_linje(self.vakt, 'i fjor', bruker=self.bruker)
        Logglinje.objects.filter(pk=gammel.pk).update(
            registrert_at=timezone.now() - timedelta(days=731))
        services.skriv_linje(self.vakt, 'i dag', bruker=self.bruker)
        self.assertEqual(services.slett_utlopte(), 1)
        self.assertEqual(
            list(Logglinje.objects.values_list('tekst', flat=True)), ['i dag'])

    def test_klokka_gaar_fra_registrert_at_og_ikke_tidspunkt(self):
        """**En frist som lar seg flytte ved å rette et klokkeslett er ingen
        frist.** `tidspunkt` er korrigerbart; `registrert_at` er det ikke."""
        linje = services.skriv_linje(self.vakt, 'fersk', bruker=self.bruker)
        Logglinje.objects.filter(pk=linje.pk).update(
            tidspunkt=timezone.now() - timedelta(days=900))
        self.assertEqual(services.slett_utlopte(), 0)

    def test_en_rettet_linje_slettes_med_kjeden_sin(self):
        """`SET_NULL` på `korrigerer`/`rot` gjør slettingen trygg uansett
        rekkefølge — men prøven finnes fordi en `PROTECT` her ville gjort
        cron-jobben rød uten at noen så det."""
        linje = services.skriv_linje(self.vakt, 'en', bruker=self.bruker)
        services.korriger(linje, bruker=self.bruker, tekst='to')
        Logglinje.objects.update(
            registrert_at=timezone.now() - timedelta(days=800))
        self.assertEqual(services.slett_utlopte(), 2)
        self.assertEqual(Logglinje.objects.count(), 0)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(TestCase):
    """Middels tyngde, som `CLAUDE.md` sier: **portene, ikke feltene.**"""

    def setUp(self):
        self.client = Client()
        self.vakt = hent_aktiv_vakt()
        self.leser = _gi_ko(_bruker('leser'), 'les')
        self.skriver = _gi_ko(_bruker('skriver'), 'skriv_full')
        self.leder = _gi_ko(_bruker('leder'), 'skriv_leder')
        self.utenfor = _bruker('utenfor')

    def _post(self, sti, data):
        return self.client.post(sti, data=json.dumps(data),
                                content_type='application/json')

    def test_les_kan_lese(self):
        self.client.force_login(self.leser)
        self.assertEqual(self.client.get('/ko/api/logg/').status_code, 200)

    def test_uten_rad_nektes(self):
        """**Fravær av rad er ingen tilgang** — det finnes ingen 'ingen'."""
        self.client.force_login(self.utenfor)
        self.assertEqual(self.client.get('/ko/api/logg/').status_code, 403)

    def test_les_kan_ikke_skrive(self):
        self.client.force_login(self.leser)
        svar = self._post('/ko/api/logg/ny/', {'tekst': 'nei'})
        self.assertEqual(svar.status_code, 403)
        self.assertEqual(Logglinje.objects.count(), 0)

    def test_skriv_full_kan_skrive(self):
        self.client.force_login(self.skriver)
        svar = self._post('/ko/api/logg/ny/', {'tekst': 'kollaps scene sør'})
        self.assertEqual(svar.status_code, 201)
        self.assertEqual(Logglinje.objects.get().tekst, 'kollaps scene sør')

    def test_skriv_full_kan_ikke_fjerne(self):
        """Skillet mot `skriv_leder` er **hva slags skade en feil gjør**: den
        som fører kan rette tilbake, fordi en retting er en ny rad. Den som
        fjerner tømmer innholdet for godt."""
        linje = services.skriv_linje(self.vakt, 'noe', bruker=self.skriver)
        self.client.force_login(self.skriver)
        svar = self._post(f'/ko/api/logg/{linje.pk}/fjern/', {'confirm': True})
        self.assertEqual(svar.status_code, 403)
        linje.refresh_from_db()
        self.assertEqual(linje.tekst, 'noe')

    def test_skriv_leder_kan_fjerne(self):
        linje = services.skriv_linje(self.vakt, 'Kari Hansen', bruker=self.skriver)
        self.client.force_login(self.leder)
        svar = self._post(f'/ko/api/logg/{linje.pk}/fjern/', {'confirm': True})
        self.assertEqual(svar.status_code, 200)
        linje.refresh_from_db()
        self.assertEqual(linje.tekst, '')

    def test_fjerning_uten_confirm_avvises(self):
        """Kravet ligger server-side og ikke bare som et vindu i nettleseren:
        en klient som går utenom grensesnittet skal møte den samme døra."""
        linje = services.skriv_linje(self.vakt, 'Kari Hansen', bruker=self.skriver)
        self.client.force_login(self.leder)
        svar = self._post(f'/ko/api/logg/{linje.pk}/fjern/', {})
        self.assertEqual(svar.status_code, 400)
        linje.refresh_from_db()
        self.assertEqual(linje.tekst, 'Kari Hansen')

    def test_fjerning_skriver_en_auditrad_uten_teksten(self):
        """**Sto teksten i auditraden, ville den ligget der i 730 dager og
        inngangen vært et skuespill.** Samme valg som
        `FELT_UTEN_VERDILOGGING` tar for `notat` i vaktlista.
        """
        from audit.models import AuditLog
        linje = services.skriv_linje(self.vakt, 'Kari Hansen 41',
                                     bruker=self.skriver)
        self.client.force_login(self.leder)
        self._post(f'/ko/api/logg/{linje.pk}/fjern/', {'confirm': True})
        rad = AuditLog.objects.get(table_name='ko_logglinje')
        self.assertEqual(rad.user, self.leder)
        self.assertNotIn('Kari', rad.new_value)
        self.assertNotIn('Kari', rad.old_value or '')

    def test_retting_av_samme_linje_to_ganger_gir_409(self):
        """409 og ikke 400: det er en konflikt om en tilstand, ikke en feil i
        det som ble sendt, og operatøren skal se at hun må lese den nye
        versjonen før hun retter videre."""
        linje = services.skriv_linje(self.vakt, 'en', bruker=self.skriver)
        self.client.force_login(self.skriver)
        self._post(f'/ko/api/logg/{linje.pk}/rett/', {'tekst': 'to'})
        svar = self._post(f'/ko/api/logg/{linje.pk}/rett/', {'tekst': 'tre'})
        self.assertEqual(svar.status_code, 409)

    def test_tom_linje_avvises_med_400(self):
        self.client.force_login(self.skriver)
        svar = self._post('/ko/api/logg/ny/', {'tekst': '   '})
        self.assertEqual(svar.status_code, 400)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PollingenTests(TestCase):
    """`?siden=<id>` (§7.1), og det svaret den ikke kan gi uten hjelp."""

    def setUp(self):
        self.client = Client()
        self.vakt = hent_aktiv_vakt()
        self.leder = _gi_ko(_bruker('leder'), 'skriv_leder')
        self.client.force_login(self.leder)

    def _logg(self, siden=None):
        sti = '/ko/api/logg/' + (f'?siden={siden}' if siden is not None else '')
        return json.loads(self.client.get(sti).content)

    def test_siden_gir_bare_det_nye(self):
        en = services.skriv_linje(self.vakt, 'en', bruker=self.leder)
        services.skriv_linje(self.vakt, 'to', bruker=self.leder)
        data = self._logg(siden=en.pk)
        self.assertEqual([l['tekst'] for l in data['data']], ['to'])

    def test_fjernede_sendes_selv_om_de_er_gamle(self):
        """**Sletteinngangen endrer en rad i stedet for å legge til en ny**, så
        den har ingen ny id og ville aldri kommet med i et `?siden=`-svar.
        Uten lista ville teksten blitt stående på hver annen operatørs skjerm
        til hun lastet siden på nytt.
        """
        linje = services.skriv_linje(self.vakt, 'Kari Hansen', bruker=self.leder)
        ny = services.skriv_linje(self.vakt, 'senere', bruker=self.leder)
        services.fjern(linje, bruker=self.leder)
        data = self._logg(siden=ny.pk)
        self.assertEqual(data['data'], [])
        self.assertIn(linje.pk, data['fjernede'])

    def test_fjernet_tekst_sendes_aldri_ut(self):
        linje = services.skriv_linje(self.vakt, 'Kari Hansen', bruker=self.leder)
        services.fjern(linje, bruker=self.leder)
        raa = self.client.get('/ko/api/logg/').content.decode()
        self.assertNotIn('Kari Hansen', raa)

    def test_soppel_i_siden_gir_400_ikke_500(self):
        self.assertEqual(self.client.get('/ko/api/logg/?siden=igaar').status_code,
                         400)

    def test_systemlinja_kommer_ferdig_tegnet_ut(self):
        """**Sømmen mellom `_til_dict` og `systemlinjer.tegn()`.**

        Linja lagres som kode + data nettopp for at ordlyden skal kunne rettes
        uten at historikken skrives om — men *tegningen* skjer på serveren.
        Gjorde klienten den, ville malen for hver setning ligget to steder, og
        utskriften av loggen fått en annen ordlyd enn skjermen. Prøvene på
        `tegn()` kaller funksjonen direkte; denne går gjennom HTTP.
        """
        services.systemlinje(self.vakt, 'oppdrag_status', {
            'oppdragsnummer': 45, 'enhet': 'HGSD 56', 'status_navn': 'Fremme'})
        linje = self._logg()['data'][0]
        self.assertEqual(linje['kilde'], KILDE_SYSTEM)
        # `O45`, ikke `#45`, fra pulje 5 (§6) — formen bor i `oppdrag.services.oppdragsnr`.
        self.assertEqual(linje['tekst'], 'HGSD 56: Fremme (O45)')
        self.assertEqual(linje['forfatter'], '')

    def test_bare_aktiv_vakt(self):
        """`les` betyr «denne vakta». Tidligere vakters logg er `skriv_leder`
        og får sin egen flate i pulje 3 — men scopet må stå fra første linje,
        ellers er det ikke et scope, det er et filter noen kan glemme."""
        from core.models import Vakt
        gammel = Vakt.objects.create(navn='i fjor', year=2025,
                                     startet=timezone.now())
        Logglinje.objects.create(vakt=gammel, tidspunkt=timezone.now(),
                                 tekst='fjorårets linje')
        services.skriv_linje(self.vakt, 'i år', bruker=self.leder)
        data = self._logg()
        self.assertEqual([l['tekst'] for l in data['data']], ['i år'])
