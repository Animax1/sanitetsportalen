"""Fase 5c: et varsel fra en annen portal bytter portal når det åpnes (§4.4).

Lenken i varselet er en sti som `/oppdrag/`, og den gjelder portalen sesjonen
står i. Uten byttet åpner et varsel om Brann Standards oppdrag.
"""
from __future__ import annotations

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, Portaltilgang
from core.models import Notification, Vaktportal
from core.portal import SESJON_NOKKEL, eneste_portal
from patients.js_test_utils import JS_DIR, build_harness, node_available, read_js, run_node


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VarseletByttetPortalTests(TestCase):

    def setUp(self):
        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.kari = CustomUser.objects.create_user(username='kari', password='x',
                                                   must_change_password=False)
        for p in (self.standard, self.brann):
            Portaltilgang.objects.create(bruker=self.kari, portal=p)
        self.c = Client()
        self.c.force_login(self.kari)
        self._sta_i(self.standard)

    def _sta_i(self, portal):
        sesjon = self.c.session
        sesjon[SESJON_NOKKEL] = portal.pk
        sesjon.save()

    def _varsel(self, portal):
        return Notification.objects.create(user=self.kari, title='Nytt oppdrag',
                                           url='/oppdrag/', portal=portal)

    def test_aapningen_bytter_til_varselets_portal(self):
        n = self._varsel(self.brann)
        svar = self.c.get(f'/varsler/{n.pk}/lest/')
        self.assertRedirects(svar, '/oppdrag/', fetch_redirect_response=False)
        self.assertEqual(self.c.session[SESJON_NOKKEL], self.brann.pk)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_samme_portal_rorer_ingenting(self):
        n = self._varsel(self.standard)
        self.c.get(f'/varsler/{n.pk}/lest/')
        self.assertEqual(self.c.session[SESJON_NOKKEL], self.standard.pk)

    def test_varsel_uten_portal_rorer_ingenting(self):
        n = self._varsel(None)
        svar = self.c.get(f'/varsler/{n.pk}/lest/')
        self.assertRedirects(svar, '/oppdrag/', fetch_redirect_response=False)
        self.assertEqual(self.c.session[SESJON_NOKKEL], self.standard.pk)

    def test_en_portal_kontoen_ikke_er_med_i_aapnes_ikke(self):
        n = self._varsel(self.brann)
        Portaltilgang.objects.filter(bruker=self.kari, portal=self.brann).delete()
        svar = self.c.get(f'/varsler/{n.pk}/lest/')
        self.assertRedirects(svar, '/varsler/', fetch_redirect_response=False)
        self.assertEqual(self.c.session[SESJON_NOKKEL], self.standard.pk)

    def test_en_deaktivert_portal_aapnes_ikke(self):
        n = self._varsel(self.brann)
        Vaktportal.objects.filter(pk=self.brann.pk).update(er_aktiv=False)
        svar = self.c.get(f'/varsler/{n.pk}/lest/')
        self.assertRedirects(svar, '/varsler/', fetch_redirect_response=False)

    def test_bjella_sier_hvilke_varsler_som_er_fra_en_annen_portal(self):
        b = self._varsel(self.brann)
        s = self._varsel(self.standard)
        data = {v['id']: v for v in self.c.get('/api/varsler/').json()['notifications']}
        self.assertTrue(data[b.pk]['annen_portal'])
        self.assertFalse(data[s.pk]['annen_portal'])

    def test_med_en_portal_er_ingenting_annen(self):
        Portaltilgang.objects.filter(bruker=self.kari, portal=self.brann).delete()
        n = self._varsel(self.brann)
        data = self.c.get('/api/varsler/').json()['notifications']
        self.assertFalse([v for v in data if v['id'] == n.pk][0]['annen_portal'])


class BjellasRegelTests(TestCase):

    def test_blir_paa_siden(self):
        if not node_available():
            self.skipTest('node mangler')
        harness = build_harness(((JS_DIR / 'notifications.js', ('blirPaaSiden',)),))
        run_node(harness, """
          assert(blirPaaSiden({url: '/oppdrag/', modul: 'oppdrag'}, 'oppdrag') === true, 'samme modul');
          assert(blirPaaSiden({url: '/oppdrag/', modul: 'oppdrag'}, 'ko') === false, 'annen modul');
          assert(blirPaaSiden({url: '/oppdrag/', modul: 'oppdrag', annenPortal: true}, 'oppdrag')
                 === false, 'annen portal navigerer');
          assert(blirPaaSiden({url: '', modul: 'oppdrag', annenPortal: true}, 'ko') === true,
                 'ingen lenke: merk lest her');
          assert(blirPaaSiden({url: '/x/', modul: ''}, '') === false, 'tom modul er ikke samme');
        """)

    def test_klikket_gaar_gjennom_regelen(self):
        """Gjennom den ekte inngangen: bjella åpnes, lista tegnes, varselet
        klikkes. Testen over kaller `blirPaaSiden()` selv, så kallstedet kunne
        sluttet å bruke den uten at noe ble rødt (CLAUDE.md, «tre måter»)."""
        if not node_available():
            self.skipTest('node mangler')
        stubb = """
          function el() {
            return {listeners: {}, dataset: {}, classList: {toggle() {}, remove() {}},
                    addEventListener(t, f) { this.listeners[t] = f; },
                    querySelector() { return null; }, querySelectorAll() { return []; },
                    innerHTML: ''};
          }
          const E = {'notification-badge': el(), 'notif-list': el(),
                     'notif-mark-all-btn': el(), 'notif-bell-btn': el()};
          const varselet = el();
          varselet.dataset = {id: '5', url: '/pasienter/', module: 'patients', annenPortal: '1'};
          E['notif-list'].querySelectorAll = () => [varselet];
          globalThis.document = {getElementById: (id) => E[id] || null, querySelector: () => null,
                                 addEventListener() {}, visibilityState: 'hidden'};
          globalThis.window = {location: {pathname: '/pasienter/', href: ''}};
          globalThis.setInterval = () => 0;
          const kalt = [];
          globalThis.fetch = async (url) => { kalt.push(url); return {ok: true, json: async () => (
            {notifications: [{id: 5, url: '/pasienter/', module_slug: 'patients',
                              annen_portal: true, title: 't', is_read: false,
                              created_at: '2026-10-18T10:00:00Z'}], unread_count: 1})}; };
        """
        run_node(read_js(JS_DIR / 'notifications.js'), """
          await E['notif-bell-btn'].listeners['show.bs.dropdown']();
          assert(E['notif-list'].innerHTML.includes('data-annen-portal="1"'),
                 'lista bærer flagget til klikket');
          await varselet.listeners.click();
          assert(window.location.href === '/varsler/5/lest/',
                 'samme modul, annen portal: skal navigere, fikk ' + window.location.href
                 + ' og ' + JSON.stringify(kalt));
        """, preamble=stubb)
