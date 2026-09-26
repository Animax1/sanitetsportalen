"""Sesjonsdekodingen i `core.sesjoner` (26. sep. 2026, E5).

Fire kopier, tre feilhåndteringer. Det som betyr noe er `slett_brukerens_sesjoner`:
den kjøres ved passordbytte, frys og sletting, og en sesjon den hopper over er
en innlogging som overlever det den skulle avslutte.
"""
from __future__ import annotations

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase

from accounts.models import CustomUser
from core.sesjoner import bruker_id_i, dekod, slett_brukerens_sesjoner


def _sesjon(bruker_id=None, **data):
    store = SessionStore()
    if bruker_id is not None:
        store['_auth_user_id'] = str(bruker_id)
    for k, v in data.items():
        store[k] = v
    store.create()
    return store.session_key


def _raa_sesjon(nyttelast):
    """En sesjon med gyldig signatur rundt noe som ikke er et objekt."""
    from django.core import signing
    store = SessionStore()
    store.create()
    kodet = signing.dumps(nyttelast, salt=store.key_salt, serializer=store.serializer,
                          compress=True)
    Session.objects.filter(session_key=store.session_key).update(session_data=kodet)
    return store.session_key


class DekodTests(TestCase):

    def test_ikke_et_objekt_gir_tom_dict(self):
        for nyttelast in ([1, 2], 'x', None, 7):
            sesjon = Session.objects.get(session_key=_raa_sesjon(nyttelast))
            self.assertEqual(dekod(sesjon), {}, nyttelast)

    def test_vanlig_sesjon(self):
        sesjon = Session.objects.get(session_key=_sesjon(5, noe='x'))
        self.assertEqual(dekod(sesjon)['noe'], 'x')

    def test_bruker_id(self):
        self.assertEqual(bruker_id_i({'_auth_user_id': '5'}), 5)
        for data in ({}, {'_auth_user_id': 'abc'}, {'_auth_user_id': None}):
            self.assertIsNone(bruker_id_i(data), data)


class SlettBrukerensSesjonerTests(TestCase):

    def setUp(self):
        self.a = CustomUser.objects.create_user(username='ses_a', password='x')
        self.b = CustomUser.objects.create_user(username='ses_b', password='x')

    def _finnes(self, nokkel):
        return Session.objects.filter(session_key=nokkel).exists()

    def test_sletter_bare_brukerens_og_sparer_unntaket(self):
        a1, a2, a3 = _sesjon(self.a.pk), _sesjon(self.a.pk), _sesjon(self.a.pk)
        b1, anonym = _sesjon(self.b.pk), _sesjon()
        self.assertEqual(slett_brukerens_sesjoner(self.a, unntatt=a1), 2)
        self.assertTrue(self._finnes(a1))
        self.assertFalse(self._finnes(a2))
        self.assertFalse(self._finnes(a3))
        self.assertTrue(self._finnes(b1))
        self.assertTrue(self._finnes(anonym))

    def test_uten_unntak_gaar_alle(self):
        a1 = _sesjon(self.a.pk)
        slett_brukerens_sesjoner(self.a)
        self.assertFalse(self._finnes(a1))

    def test_en_uleselig_sesjon_stopper_ikke_slettingen(self):
        """Før E5 kastet `.get()` på en sesjon som ikke var et objekt, og
        passordbyttet stoppet før resten av brukerens sesjoner var borte."""
        _raa_sesjon([1])
        a1 = _sesjon(self.a.pk)
        slett_brukerens_sesjoner(self.a)
        self.assertFalse(self._finnes(a1))
