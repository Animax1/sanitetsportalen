"""Verdilistefabrikken — det som ble likt da de to kopiene ble én (26. sep. 2026, E2).

Hver rad prøver én av forskjellene fra tabellen i `core/verdilister.py`, i den
modulen der den *før* var feil, gjennom den ekte URL-en. Resten av oppførselen
— nivåene, 409 ved bruk, rekkefølgen — holdes av modulenes egne tester, som
gikk uendret gjennom byttet.
"""
import json

from django.test import RequestFactory, TestCase, override_settings

from accounts.models import CustomUser
from core.verdilister import Verdiliste, lag_views
from ko.models import Ansvarsomraade
from oppdrag.models import Enhet, Enhetstype, Lokasjon


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class FabrikkenTests(TestCase):

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='vl_admin', password='x', role='admin', must_change_password=False)
        self.client.force_login(self.admin)

    def _post(self, url, **kropp):
        return self.client.post(url, data=json.dumps(kropp), content_type='application/json')

    def test_oppdrag_navnet_er_unikt_uten_hensyn_til_store_smaa(self):
        """Var eksakt i oppdrag: «Scene nord» og «scene nord» i samme nedtrekk."""
        Lokasjon.objects.create(navn='Scene nord')
        res = self._post('/oppdrag/api/lokasjoner/', navn='scene nord')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('finnes allerede', res.json()['message'])

    def test_oppdrag_for_langt_navn_er_400_ikke_500(self):
        """Oppdrag sjekket ikke lengden; PostgreSQL avviser for lange verdier
        med en databasefeil, altså 500."""
        maks = Lokasjon._meta.get_field('navn').max_length
        res = self._post('/oppdrag/api/lokasjoner/', navn='x' * (maks + 1))
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn(f'maks {maks}', res.json()['message'])

    def test_ko_ukjent_id_gir_json_404(self):
        """KO brukte `get_object_or_404` — en HTML-side til et JSON-kall."""
        res = self.client.put('/ko/api/ansvarsomraader/987654/', data='{}',
                              content_type='application/json')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()['message'], 'Ikke funnet')

    def test_ko_lista_har_etag(self):
        Ansvarsomraade.objects.create(navn='Sanitet', rekkefolge=10)
        forste = self.client.get('/ko/api/ansvarsomraader/')
        self.assertTrue(forste.has_header('ETag'))
        igjen = self.client.get('/ko/api/ansvarsomraader/', HTTP_IF_NONE_MATCH=forste['ETag'])
        self.assertEqual(igjen.status_code, 304)

    def test_beskyttet_rad_gir_409_ikke_500(self):
        """En tabell uten `i_bruk` og en `PROTECT`-relasjon: KO fanget ikke
        `ProtectedError`, så slettingen ble 500."""
        type_ = Enhetstype.objects.create(navn='Prøvetype', rekkefolge=10)
        Enhet.objects.create(navn='Bil på prøvetypen', enhetstype=type_)
        _, detalj, _ = lag_views(modul='oppdrag', liste=Verdiliste(Enhetstype), slug='prove',
                                 kan_lede=lambda user: True, nekt='nei', gruppe='prove:')
        req = RequestFactory().delete('/x/', data=json.dumps({'confirm': True}),
                                      content_type='application/json')
        req.user = self.admin
        res = detalj(req, pk=type_.pk)
        self.assertEqual(res.status_code, 409, res.content)
        self.assertTrue(Enhetstype.objects.filter(pk=type_.pk).exists())
