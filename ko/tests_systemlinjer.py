"""Løftet av systemhendelser inn i KO-loggen (pulje 2).

To ting prøves, og de svarer på hver sin fare:

1. **At lista er en kontrakt.** En kode som ikke står i `KODER` skrives ikke,
   og en type i `Enhetshendelse` som ingen har tatt stilling til, sier fra.
   Uten dette ville en ny hendelsestype i oppdragsmodulen falt stille ut av
   loggen — og en logg som mangler noe uten å si det, er verre enn ingen.
2. **At løftet faktisk skjer når noe gjøres.** Regel 3 i `CLAUDE.md` om
   mutasjoner: muter kallstedet, ikke bare funksjonen. Her betyr det at
   prøvene går gjennom `oppdrag.services`, ikke gjennom `systemlinje()`.
"""
from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from core.vakt import hent_aktiv_vakt
from ko import signals, systemlinjer
from ko.models import KILDE_SYSTEM, Logglinje
from oppdrag import choices, services as oservices
from oppdrag.models import Enhet, Enhetshendelse, Lokasjon, Oppdrag


class ListaErEnKontraktTests(TestCase):

    def test_hver_kode_har_en_begrunnelse(self):
        """Som `NOKLER_UTEN_AUDIT`: lista skal være eksplisitt **og**
        begrunnet. En kode uten begrunnelse er en kode ingen kan vurdere om
        hører hjemme der."""
        uten = [k for k, hvorfor in systemlinjer.KODER.items() if not hvorfor.strip()]
        self.assertEqual(uten, [])

    def test_hver_kode_tegner_noe(self):
        """En kode `tegn()` ikke kjenner ville gitt en tom linje i loggen — en
        rad som sier at noe skjedde, uten å si hva."""
        for kode in systemlinjer.KODER:
            with self.subTest(kode=kode):
                self.assertNotEqual(systemlinjer.tegn(kode, {'enhet': 'HGSD 56'}), '')

    def test_ukjent_kode_gir_tom_streng_og_ikke_et_krasj(self):
        """En rad skrevet av en nyere versjon skal ikke ta ned loggen for den
        som leser den med en eldre."""
        self.assertEqual(systemlinjer.tegn('noe_nytt', {}), '')

    def test_hver_enhetshendelse_er_vurdert(self):
        """**Den viktigste prøven i fila.**

        `Enhetshendelse.TYPER` er oppdragsmodulens liste, og den vokser der og
        ikke her. En ny type som verken løftes eller står som bevisst utelatt,
        ville forsvunnet ut av loggen uten at noe ble rødt — nøyaktig den
        stillheten en håndholdt liste forfaller i.
        """
        kjente = set(signals.ENHETSHENDELSER) | set(signals.ENHETSHENDELSER_UTELATT)
        faktiske = {verdi for verdi, _ in Enhetshendelse.TYPER}
        self.assertEqual(faktiske - kjente, set(), (
            'Nye typer i oppdrag.Enhetshendelse som ingen har tatt stilling '
            'til. Legg dem i ENHETSHENDELSER (løftes) eller i '
            'ENHETSHENDELSER_UTELATT med en begrunnelse.'))

    def test_en_ukjent_kode_lar_seg_ikke_skrive(self):
        """**Lista er en kontrakt, og sperren er den som gjør den til det.**

        Mutanten som fjernet `if kode not in KODER` overlevde første
        mutasjonsrunde (17. sep. 2026): lista var dokumentasjon, ikke en port.
        Uten sperren kan en skrivefeil i en signalmottaker legge en rad i
        loggen som `tegn()` ikke kjenner — og den blir en tom linje, altså en
        rad som sier at noe skjedde uten å si hva.
        """
        from ko import services

        with self.assertRaises(services.Ugyldig):
            services.systemlinje(hent_aktiv_vakt(), 'oppdrag_omdopt', {})

    def test_ingen_kode_peker_paa_noe_som_ikke_finnes(self):
        """Andre veien: en omdøpt konstant skal ikke gi et løft til en kode
        `tegn()` aldri har hørt om."""
        for kode in signals.ENHETSHENDELSER.values():
            self.assertIn(kode, systemlinjer.KODER)


class LoftetSkjerTests(TestCase):
    """Gjennom `oppdrag.services`, ikke gjennom `systemlinje()`.

    Kaller testen hjelperen selv, kan kallstedet fjernes uten at noe blir rødt
    — regel 3 i `CLAUDE.md`, og nøyaktig feilen `planleggerSikreLinjer()` gikk
    i. Her *er* kallstedet hele mekanismen.
    """

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.konto = CustomUser.objects.create_user(
            username='hgsd56', password='x', must_change_password=False,
            er_delt_konto=True)
        self.operator = CustomUser.objects.create_user(
            username='ko1', password='x', must_change_password=False)
        self.enhet = Enhet.objects.create(navn='HGSD 56', user=self.konto)
        self.lokasjon = Lokasjon.objects.create(navn='Scene sør')

    def _opprett(self):
        oppdrag = Oppdrag.objects.create(
            vakt=self.vakt,
            oppdragsnummer=oservices.neste_oppdragsnummer(self.vakt),
            enhet=self.enhet,
            problemstilling='Brystsmerter',
            hastegrad=choices.HASTEGRAD[0],
            lokasjon=self.lokasjon,
        )
        # `Oppdrag.save()` oppretter koblingsraden selv — enheten er varslet
        # i det oppdraget finnes. Et eget `varsle_enhet` her ville vært en
        # dublett, og testen ville målt noe brukeren aldri gjør.
        return oppdrag

    def _koder(self):
        return list(Logglinje.objects
                    .filter(kilde=KILDE_SYSTEM)
                    .values_list('systemkode', flat=True))

    def test_opprettelse_gir_en_linje(self):
        self._opprett()
        self.assertIn(systemlinjer.OPPDRAG_OPPRETTET, self._koder())

    def test_linja_baerer_frosne_verdier_og_ikke_en_peker(self):
        """**Ingen FK til `Oppdrag`**: `arkiver_vakt` sletter oppdragsradene
        når vakta arkiveres, og en peker hit ville vært en felle uansett
        `on_delete`. Linja skal fortsatt kunne leses etter det."""
        self._opprett()
        linje = Logglinje.objects.get(systemkode=systemlinjer.OPPDRAG_OPPRETTET)
        self.assertEqual(linje.systemdata['lokasjon'], 'Scene sør')
        self.assertEqual(linje.systemdata['problemstilling'], 'Brystsmerter')

    def test_varsling_gir_en_linje_med_kallesignalet(self):
        self._opprett()
        linje = Logglinje.objects.get(systemkode=systemlinjer.ENHET_VARSLET)
        self.assertEqual(linje.systemdata['enhet'], 'HGSD 56')

    def test_kallesignalet_overlever_at_enheten_doepes_om(self):
        """§4.7: kallesignalet fryses på linja. Besetningen gjør det ikke —
        en retting i vaktlista i etterkant retter som regel virkeligheten."""
        self._opprett()
        self.enhet.navn = 'Haugesund 56'
        self.enhet.save(update_fields=['navn'])
        linje = Logglinje.objects.get(systemkode=systemlinjer.ENHET_VARSLET)
        self.assertIn('HGSD 56', systemlinjer.tegn(linje.systemkode,
                                                   linje.systemdata))

    def test_statusmelding_gir_en_linje(self):
        oppdrag = self._opprett()
        oservices.sett_status(oppdrag, choices.RYKKER_UT, bruker=self.konto,
                              enhet=self.enhet)
        self.assertIn(systemlinjer.OPPDRAG_STATUS, self._koder())

    def test_bilen_selv_er_ikke_fort_av_ko(self):
        """§3.1: skillet mellom «bilen sa det» og «KO førte det» skal være
        synlig i loggen — og det er en påstand, så den skal være riktig."""
        oppdrag = self._opprett()
        oservices.sett_status(oppdrag, choices.RYKKER_UT, bruker=self.konto,
                              enhet=self.enhet)
        linje = Logglinje.objects.filter(
            systemkode=systemlinjer.OPPDRAG_STATUS).latest('pk')
        self.assertFalse(linje.systemdata['fort_av_ko'])
        self.assertNotIn('ført av KO',
                         systemlinjer.tegn(linje.systemkode, linje.systemdata))

    def test_operatoeren_er_fort_av_ko(self):
        """§4.6: «det skal stå i sporet at KO avsluttet på enhetens vegne»."""
        oppdrag = self._opprett()
        oservices.sett_status(oppdrag, choices.RYKKER_UT, bruker=self.operator,
                              enhet=self.enhet)
        linje = Logglinje.objects.filter(
            systemkode=systemlinjer.OPPDRAG_STATUS).latest('pk')
        self.assertTrue(linje.systemdata['fort_av_ko'])
        self.assertIn('ført av KO',
                      systemlinjer.tegn(linje.systemkode, linje.systemdata))

    def test_ukjent_konto_paastaar_ikke_overstyring(self):
        """«Ukjent» skal ikke tegnes som en overstyring: en påstand om at KO
        overstyrte, på en linje der vi ikke vet, er verre enn ingen påstand."""
        self.enhet.user = None
        self.enhet.save(update_fields=['user'])
        oppdrag = self._opprett()
        oservices.sett_status(oppdrag, choices.RYKKER_UT, bruker=self.operator,
                              enhet=self.enhet)
        linje = Logglinje.objects.filter(
            systemkode=systemlinjer.OPPDRAG_STATUS).latest('pk')
        self.assertFalse(linje.systemdata['fort_av_ko'])

    def test_korrigert_tidspunkt_blir_sin_egen_linje(self):
        oppdrag = self._opprett()
        melding = oservices.sett_status(oppdrag, choices.RYKKER_UT,
                                        bruker=self.konto, enhet=self.enhet)
        oservices.korriger_tidspunkt(
            melding, melding.tidspunkt - timezone.timedelta(minutes=5),
            bruker=self.operator)
        self.assertIn(systemlinjer.TIDSPUNKT_KORRIGERT, self._koder())

    def test_enhetshendelse_loftes(self):
        oppdrag = self._opprett()
        Enhetshendelse.objects.create(
            oppdrag=oppdrag, enhet=self.enhet,
            type=Enhetshendelse.AVVENTER, av=self.operator)
        self.assertIn(systemlinjer.ENHET_AVVENTER, self._koder())

    def test_trenger_ressurs_er_et_flagg_og_ikke_en_linje_til(self):
        """Regel 3: én linje per ting som skjedde. «Bilen avbrøt» og
        «oppdraget trenger ny ressurs» er én hendelse sett fra hver sin
        side."""
        oppdrag = self._opprett()
        oppdrag.trenger_ressurs = True
        oppdrag.save(update_fields=['trenger_ressurs'])
        Enhetshendelse.objects.create(
            oppdrag=oppdrag, enhet=self.enhet,
            type=Enhetshendelse.AVBRUTT, av=self.operator)
        linje = Logglinje.objects.get(systemkode=systemlinjer.ENHET_AVBROT)
        self.assertTrue(linje.systemdata['trenger_ressurs'])
        self.assertIn('trenger ny ressurs',
                      systemlinjer.tegn(linje.systemkode, linje.systemdata))
        self.assertEqual(
            self._koder().count(systemlinjer.ENHET_AVBROT), 1)

    def test_systemlinjer_har_ingen_forfatter(self):
        """Linja er ikke ført av noen, den *skjedde*. Et brukernavn her ville
        lest som at operatøren skrev setningen."""
        self._opprett()
        for linje in Logglinje.objects.filter(kilde=KILDE_SYSTEM):
            self.assertEqual(linje.forfatter_navn, '')

    def test_oppsett_loftes_ikke(self):
        """§4.2 sitt eget eksempel: «Enhetstype fikk nytt navn» hører ikke
        hjemme i loggen. Regel 1 — situasjon, ikke oppsett."""
        Lokasjon.objects.create(navn='Scene nord')
        self.enhet.navn = 'HGSD 57'
        self.enhet.save(update_fields=['navn'])
        self.assertEqual(Logglinje.objects.count(), 0)


class MottakerneKasterIkkeTests(TestCase):
    """**En KO-logg som ikke lar seg skrive skal ikke ta ned en stempling.**

    Bilen er det operative, loggen er dokumentasjonen. Motsatt prioritering
    ville gjort loggen til en ny grunn til at oppdragsmodulen ikke virker.
    """

    def test_feil_i_loftet_stopper_ikke_oppdraget(self):
        from unittest.mock import patch

        vakt = hent_aktiv_vakt()
        enhet = Enhet.objects.create(navn='HGSD 56')
        lokasjon = Lokasjon.objects.create(navn='Scene sør')
        with patch('ko.signals.systemlinje', side_effect=RuntimeError('nei')):
            oppdrag = Oppdrag.objects.create(
                vakt=vakt, oppdragsnummer=1, enhet=enhet,
                problemstilling='Brystsmerter', lokasjon=lokasjon,
                hastegrad=choices.HASTEGRAD[0])
        self.assertTrue(Oppdrag.objects.filter(pk=oppdrag.pk).exists())
        self.assertEqual(Logglinje.objects.count(), 0)
