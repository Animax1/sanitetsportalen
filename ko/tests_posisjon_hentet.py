"""«Hent posisjon» i KO-loggen (C3, André 19. okt. 2026: «jeg vil ha det logget»).

Hver henting gir en systemlinje med hvem som spurte — én bil som én linje, «fra
alle» i en gruppe som **én** linje med antallet. I strømmen alltid; i hendelsen
også når bilen står på et oppdrag som hører til en. Aldri koordinater. Prøvd
gjennom den ekte inngangen, knappenes endepunkt i oppdragsmodulen.
"""
from __future__ import annotations

from django.test import Client, override_settings

from core.models import ModuleSettings
from ko import services, systemlinjer
from ko.models import KILDE_SYSTEM, Logglinje
from oppdrag import choices, posisjon
from oppdrag import services as oservices
from oppdrag.models import Enhet, Enhetstype
from oppdrag.test_helpers import lag_oppdrag

from .tests_hendelseslogg import _bruker, _gi
from .tests_tavle import _Grunnlag

KOBLET = {'KART_URL': 'https://kart.example.no', 'KART_HMAC_NOKKEL': 'k' * 64}


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False, **KOBLET)
class HentPosisjonILoggenTests(_Grunnlag):

    def setUp(self):
        super().setUp()
        posisjon.lagre({'aktiv': True})
        Enhet.objects.filter(pk=self.enhet.pk).update(user=_bruker('hgsd56'))
        _gi(self.operator, 'oppdrag', 'skriv_full')
        self.klient = Client()
        self.klient.force_login(self.operator)

    def _hent(self, enhet=None):
        return self.klient.post(f'/oppdrag/api/enheter/{(enhet or self.enhet).pk}/hent-posisjon/',
                                data='{}', content_type='application/json')

    def _alle(self, kropp='{}'):
        return self.klient.post('/oppdrag/api/enheter/hent-posisjon/', data=kropp,
                                content_type='application/json')

    def _linjer(self):
        return list(Logglinje.objects.filter(kilde=KILDE_SYSTEM,
                                             systemkode=systemlinjer.POSISJON_HENTET).order_by('id'))

    def test_en_bil_gir_en_linje_med_hvem_i_stroemmen(self):
        self.assertEqual(self._hent().status_code, 202)
        (linje,) = self._linjer()
        self.assertIsNone(linje.hendelse_id)
        self.assertEqual(linje.forfatter_navn, 'ko1')
        self.assertEqual(linje.systemdata, {'navn': 'HGSD 56'}, 'aldri koordinater')
        self.assertEqual(systemlinjer.tegn(linje.systemkode, linje.systemdata),
                         'Hent posisjon: HGSD 56')

    def test_hver_henting_logges_ogsaa_den_andre(self):
        self._hent()
        self._hent()
        self.assertEqual(len(self._linjer()), 2, 'C3: hver henting, ikke samlet')

    def test_bil_paa_et_oppdrag_i_en_hendelse_faar_linja_i_hendelsen(self):
        h = services.opprett_hendelse(self.vakt, 'Fall', bruker=self.operator, lokasjon=self.park)
        o = lag_oppdrag(vakt=self.vakt, oppdragsnummer=oservices.neste_oppdragsnummer(self.vakt),
                        enhet=self.enhet, lokasjon=self.park, problemstilling='Fall',
                        hastegrad=choices.HASTEGRAD[0])
        oservices.sett_status(o, choices.RYKKER_UT, enhet=self.enhet)
        services.knytt_oppdrag(o, h, bruker=self.operator)
        self._hent()
        self.assertEqual(self._linjer()[0].hendelse_id, h.pk)

    def test_fra_alle_i_en_gruppe_er_en_linje_med_antallet(self):
        typen = Enhetstype.objects.create(navn='Testambulanse')
        Enhet.objects.filter(pk=self.enhet.pk).update(enhetstype=typen)
        Enhet.objects.create(navn='Karmøy 51', user=_bruker('k51'), enhetstype=typen,
                             posisjonsdeling=choices.POSISJONSDELING_AV)
        Enhet.objects.create(navn='Haugesund 57', user=_bruker('h57'), enhetstype=typen)
        self.assertEqual(self._alle('{"type": %d}' % typen.pk).status_code, 202)
        (linje,) = self._linjer()
        self.assertIsNone(linje.hendelse_id)
        self.assertEqual(linje.forfatter_navn, 'ko1')
        self.assertEqual(systemlinjer.tegn(linje.systemkode, linje.systemdata),
                         'Hent posisjon fra alle i Testambulanse: 2 av 3 biler kan svare')

    def test_fra_alle_uten_avgrensning(self):
        self._alle()
        (linje,) = self._linjer()
        self.assertEqual(systemlinjer.tegn(linje.systemkode, linje.systemdata),
                         'Hent posisjon fra alle biler på vakt: 1 av 1 biler kan svare')

    def test_avvist_henting_gir_ingen_linje(self):
        Enhet.objects.filter(pk=self.enhet.pk).update(posisjonsdeling=choices.POSISJONSDELING_AV)
        self.assertEqual(self._hent().status_code, 409)
        self.assertEqual(self._linjer(), [])

    def test_ko_av_gir_ingen_linje_men_hentingen_virker(self):
        ModuleSettings.objects.filter(slug='ko').update(enabled=False)
        self.assertEqual(self._hent().status_code, 202)
        self.assertEqual(self._linjer(), [])
