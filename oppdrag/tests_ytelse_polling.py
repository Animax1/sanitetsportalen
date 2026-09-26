"""Endepunktene som polles koster like mange spørringer for 1 og for 30 (G4).

`enheter_view` polles hvert tiende sekund fra hver fane med sentralbordet eller
KO åpen, oppdragslista og tavla like ofte. Et oppslag *per rad* er da et
oppslag per rad per poll per fane — hele vakta. Testene bygger samme scenario
med k=1 og k=3 av hvert slag (ledig, tildelt, på oppdrag, på hendelse) og krever
**samme antall spørringer**: tallet skal ikke vokse med lista.
"""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from ko.models import Hendelse, HendelseLag, Logglinje
from vaktliste.models import Vaktliste
from vaktliste.test_helpers import lag_ressurs

from . import services
from .models import Enhet, Enhetstype, Oppdrag
from .tests_views import OppdragBasis, _bruker, _klient


class SporringerVokserIkkeMedListaTests(OppdragBasis):

    def setUp(self):
        super().setUp()
        self.sentral = _klient(_bruker('sentral_g4', 'skriv_full'))
        self.type = Enhetstype.objects.create(navn='Prøvetype G4', rekkefolge=10)
        self.vl = Vaktliste.objects.create(vakt=self.vakt)
        self._n = 0

    def _hendelse(self):
        from ko.services import neste_hendelsesnummer
        return Hendelse.objects.create(vakt=self.vakt, tittel='Brann',
                                       hendelsesnummer=neste_hendelsesnummer(self.vakt))

    def _legg_til(self, k):
        """k enheter av hvert slag, og k lag på hendelser."""
        bruker = _bruker(f'op_{self._n}', 'skriv_full')
        for _ in range(k):
            self._n += 1
            ledig = Enhet.objects.create(navn=f'Ledig {self._n}', enhetstype=self.type)
            tildelt = Enhet.objects.create(navn=f'Tildelt {self._n}', enhetstype=self.type)
            ute = Enhet.objects.create(navn=f'Ute {self._n}', enhetstype=self.type)
            h = self._hendelse()
            o1 = self._oppdrag(enhet=tildelt, hendelse=h)
            o2 = self._oppdrag(enhet=ute, hendelse=h)
            services.start_oppdrag(o2, bruker=bruker, enhet=ute)
            o3 = self._oppdrag(enhet=ledig)
            services.start_oppdrag(o3, bruker=bruker, enhet=ledig)
            services.sett_status(o3, 'fremme', bruker=bruker, enhet=ledig)
            services.behandle_paa_sted(o3, bruker=bruker, enhet=ledig)
            Logglinje.objects.create(vakt=self.vakt, hendelse=h, tekst='Delt med alle',
                                     tidspunkt=timezone.now(), delt_at=timezone.now())
            lag = lag_ressurs(vaktliste=self.vl, navn=f'Lag {self._n}')
            HendelseLag.objects.create(hendelse=h, ressurs=lag, ressurs_navn=lag.navn,
                                       fra=timezone.now())
            for e in (ledig, tildelt, ute):
                lag_ressurs(vaktliste=self.vl, navn=e.navn, enhet=e)

    def _tell(self, kall):
        with CaptureQueriesContext(connection) as ctx:
            kall()
        return len(ctx)

    def _sammenlign(self, kall):
        self._legg_til(1)
        en = self._tell(kall)
        self._legg_til(2)
        tre = self._tell(kall)
        self.assertEqual(tre, en, f'{en} spørringer med k=1, {tre} med k=3')

    def test_enhetene(self):
        self._sammenlign(lambda: self.assertEqual(
            self.sentral.get('/oppdrag/api/enheter/').status_code, 200))

    def test_oppdragslista(self):
        self._sammenlign(lambda: self.assertEqual(
            self.sentral.get('/oppdrag/api/oppdrag/').status_code, 200))

    def test_historikken(self):
        self._sammenlign(lambda: self.assertEqual(
            self.sentral.get('/oppdrag/api/historikk/').status_code, 200))

    def test_opptatt_paa_tavla(self):
        from ko.tavle import opptatt
        # Samme form som `ressurser_paa_tavla` henter dem i.
        self._sammenlign(lambda: opptatt(
            list(self.vl.ressurser.select_related('gruppe', 'enhet')), self.vakt))

    # ── Bulk-svaret er enkeltsvaret ────────────────────────────────────────
    # Regelen står bare i bulk-funksjonene, men lista kjører dem med mange
    # enheter i én spørring. Da kan en enhet få en annens rad — det er det
    # disse prøver.

    def test_hvert_kort_i_lista_er_kortet_alene(self):
        self._legg_til(3)
        enheter = list(Enhet.objects.select_related('user', 'enhetstype'))
        lista = services.enhetskort_liste(enheter, self.vakt)
        for e, kort in zip(enheter, lista):
            with self.subTest(e.navn):
                self.assertEqual(kort, services.enhetskort(e, self.vakt))
        statuser = {k['status'] for k in lista}
        self.assertTrue({'ledig', 'tildelt', 'rykker_ut'} <= statuser, statuser)

    def test_delte_linjer_i_lista_er_linjene_alene(self):
        from ko.models import Linjedeling
        from .views_common import delte_linjer_for_liste
        self._legg_til(2)
        h1, h2 = Hendelse.objects.order_by('pk')[:2]
        o1 = Oppdrag.objects.filter(hendelse=h1).first()
        # En linje delt med bare ett oppdrag, og en fra en annen hendelse
        # delt med samme oppdrag — den skal ikke telle.
        egen = Logglinje.objects.create(vakt=self.vakt, hendelse=h1, tekst='Bare til deg',
                                        tidspunkt=timezone.now())
        fremmed = Logglinje.objects.create(vakt=self.vakt, hendelse=h2, tekst='Feil hendelse',
                                           tidspunkt=timezone.now())
        Linjedeling.objects.create(linje=egen, oppdrag=o1)
        Linjedeling.objects.create(linje=fremmed, oppdrag=o1)
        alle = list(Oppdrag.objects.all())
        lista = delte_linjer_for_liste(alle)
        for o in alle:
            with self.subTest(o.oppdragsnummer):
                alene = o.hendelse.delte_linjer_for(o) if o.hendelse_id else []
                self.assertEqual(lista[o.pk], alene)
        tekster = [l['tekst'] for l in lista[o1.pk]]
        self.assertIn('Bare til deg', tekster)
        self.assertNotIn('Feil hendelse', tekster)
        andre = Oppdrag.objects.filter(hendelse=h1).exclude(pk=o1.pk).first()
        self.assertNotIn('Bare til deg', [l['tekst'] for l in lista[andre.pk]])



class EnhetStatusBulkReglerTests(OppdragBasis):
    """Reglene `enhet_status_bulk` arvet fra enkeltversjonen. Mutasjonstestingen
    26. sep. 2026 viste at ingen av dem var prøvd — heller ikke før G4."""

    def setUp(self):
        super().setUp()
        self.bruker = _bruker('op_regler', 'skriv_full')

    def _info(self, enhet=None):
        return services.enhet_status_bulk([enhet or self.enhet], self.vakt)[(enhet or self.enhet).pk]

    def test_nyeste_paabegynte_vinner(self):
        from .models import Oppdragsenhet
        eldre, nyere = self._oppdrag(), self._oppdrag()
        Oppdrag.objects.filter(pk=eldre.pk).update(created_at=timezone.now() - timezone.timedelta(hours=1))
        Oppdragsenhet.objects.filter(oppdrag__in=(eldre, nyere)).update(status='fremme')
        self.assertEqual(self._info()['aktivt_oppdrag'].pk, nyere.pk)

    def test_forrige_vakt_teller_ikke(self):
        from .models import Oppdragsenhet
        gammel = self._oppdrag(vakt=self.vakt.year - 1)
        self.assertEqual(self._info()['status'], 'ledig', 'ventende fra i fjor')
        Oppdragsenhet.objects.filter(oppdrag=gammel).update(status='fremme')
        self.assertEqual(self._info()['status'], 'ledig', 'påbegynt fra i fjor')

    def test_tildelt_siden_er_forste_varsling(self):
        from .models import Oppdragsenhet
        forst, sist = self._oppdrag(), self._oppdrag()
        t = timezone.now()
        Oppdragsenhet.objects.filter(oppdrag=forst).update(varslet_at=t - timezone.timedelta(minutes=9))
        Oppdragsenhet.objects.filter(oppdrag=sist).update(varslet_at=t - timezone.timedelta(minutes=2))
        info = self._info()
        self.assertEqual((info['status'], info['antall_ventende']), ('tildelt', 2))
        self.assertEqual(info['tildelt_siden'], t - timezone.timedelta(minutes=9))

    def test_tavla_regner_fra_da_hun_selv_rykket_ut(self):
        """To biler på samme oppdrag: hver sin «fra»."""
        from ko.tavle import opptatt
        o = self._oppdrag()
        services.varsle_enhet(o, self.annen_enhet, bruker=self.bruker)
        t = timezone.now()
        services.start_oppdrag(o, bruker=self.bruker, enhet=self.enhet,
                               tidspunkt=t - timezone.timedelta(minutes=20))
        services.start_oppdrag(o, bruker=self.bruker, enhet=self.annen_enhet,
                               tidspunkt=t - timezone.timedelta(minutes=5))
        vl = Vaktliste.objects.create(vakt=self.vakt)
        a = lag_ressurs(vaktliste=vl, navn='A', enhet=self.enhet)
        b = lag_ressurs(vaktliste=vl, navn='B', enhet=self.annen_enhet)
        ut = opptatt(list(vl.ressurser.select_related('gruppe', 'enhet')), self.vakt)
        self.assertEqual(ut[a.pk]['fra'], t - timezone.timedelta(minutes=20))
        self.assertEqual(ut[b.pk]['fra'], t - timezone.timedelta(minutes=5))
