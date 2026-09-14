"""Vaktlista som fil på e-post — reserven når portalen er nede (12. sep. 2026).

Ukryptert etter vurdering: navn, korps, rolle, skift, telefon og ISSI. Ikke
e-post, notat eller merknad. Fast mottakerliste satt av admin, sending ved
«Sett i drift» og på knapp, hver utsending logget.
"""
import json
from datetime import timedelta

from django.core import mail
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from audit.models import AuditLog
from patients.js_test_utils import (
    PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness, node_available, run_node)
from core.models import AppSetting

from . import fil, services
from .models import Mannskap, Utsending, Vaktpost
from .tests_tilgang import TilgangsBasis, _bruker, _klient


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class FilBasis(TilgangsBasis):
    def setUp(self):
        super().setUp()
        self.p_hgsd.telefon = '900 00 000'
        self.p_hgsd.issi = '0012345'
        self.p_hgsd.epost = 'kari@example.org'
        self.p_hgsd.notat = 'Skal hentes 0800 — allergisk'
        self.p_hgsd.save()
        AppSetting.set(fil.MOTTAKERE_NOKKEL, 'vaktleder@example.org\nko@example.org')

    def _skift(self, ressurs, mannskap, fra=0, til=8, **felter):
        return Vaktpost.objects.create(
            ressurs=ressurs, mannskap=mannskap,
            fra_tid=self.na + timedelta(hours=fra), til_tid=self.na + timedelta(hours=til),
            **felter)


class FilaTests(FilBasis):
    def test_fila_baerer_det_den_skal_og_ikke_mer(self):
        self._skift(self.res_hgsd, self.p_hgsd, merknad='går hjem tidlig, syk')
        self._skift(self.res_karmoy, self.p_karmoy, fra=8, til=16)
        html = fil.bygg_fil(self.vl)
        for ventet in ('Kari', 'Ola', 'HGSD', 'Karmøy', '900 00 000', '0012345',
                       'Lag HGSD', 'Lag Karmøy', 'slett den etter vakta', '<!doctype html>'):
            self.assertIn(ventet, html, ventet)
        for forbudt in ('kari@example.org', 'Skal hentes', 'allergisk', 'går hjem tidlig'):
            self.assertNotIn(forbudt, html, f'«{forbudt}» skal ikke ut i en innboks')
        self.assertNotIn('<link', html, 'selvstendig: ingen eksterne stilark')
        self.assertNotIn('<script', html)

    def test_grupper_ressurser_og_rekkefolge(self):
        """Gruppa, så ressursen, så skiftene på fra, til, navn — som
        utskriftslista. Ressurser uten skift utelates."""
        self._skift(self.res_hgsd, self.p_hgsd, fra=8, til=16)
        ase = Mannskap.objects.create(navn='Åse', korps=self.hgsd)
        self._skift(self.res_hgsd, ase, fra=0, til=8)
        self._skift(self.res_hgsd, None, fra=0, til=4)      # ledig plass
        grupper = fil.rader_for(self.vl)
        ressurser = [r['navn'] for g in grupper for r in g['ressurser']]
        self.assertEqual(ressurser, ['Lag HGSD'], 'KO og Lag Karmøy har ingen skift')
        skift = grupper[0]['ressurser'][0]['skift']
        self.assertEqual([s['navn'] for s in skift], ['— ledig —', 'Åse', 'Kari'])
        self.assertTrue(skift[0]['ledig'])
        self.assertEqual(skift[0]['korps'], 'HGSD', 'ledig plass: ressursens reservasjon')
        self.assertEqual(fil.antall_skift(grupper), 3)

    def test_fila_escaper(self):
        farlig = Mannskap.objects.create(navn='<img src=x onerror=alert(1)>', korps=self.hgsd)
        self._skift(self.res_hgsd, farlig)
        html = fil.bygg_fil(self.vl)
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;img', html)

    def test_filnavnet_er_trygt(self):
        self.vl.vakt.navn = 'Sommer/Stevne 2026 æøå'
        self.vl.vakt.save()
        navn = fil.filnavn(self.vl)
        self.assertTrue(navn.startswith('vaktliste-sommerstevne-2026'), navn)
        self.assertTrue(navn.endswith('.html'))
        self.assertNotIn('/', navn)


class UtsendingTests(FilBasis):
    def test_send_fil_legger_ved_fila_og_logger(self):
        self._skift(self.res_hgsd, self.p_hgsd)
        AuditLog.objects.all().delete()
        rad = fil.send_fil(self.vl, bruker=self.vaktleder)
        self.assertEqual(rad.feil, '')
        self.assertEqual(rad.antall_rader, 1)
        self.assertEqual(rad.antall_mottakere, 2)
        self.assertEqual(rad.sendt_av, self.vaktleder)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(sorted(m.to), ['ko@example.org', 'vaktleder@example.org'])
        self.assertEqual(len(m.attachments), 1)
        navn, innhold, mimetype = m.attachments[0]
        self.assertTrue(navn.endswith('.html'))
        self.assertEqual(mimetype, 'text/html')
        self.assertIn('Kari', innhold)
        self.assertNotIn('Kari', m.body, 'kroppen bærer ingen personopplysninger')
        self.assertIn('Slett den etter vakta', m.body)
        audit = AuditLog.objects.get(table_name='vaktliste_utsending', action='CREATE')
        self.assertIn('vaktleder@example.org', audit.new_value)
        self.assertIn('sendt', audit.new_value)

    def test_uten_mottakere_sendes_ingenting_men_raden_sier_hvorfor(self):
        AppSetting.set(fil.MOTTAKERE_NOKKEL, '')
        rad = fil.send_fil(self.vl, bruker=self.vaktleder)
        self.assertIn('Ingen mottakere', rad.feil)
        self.assertEqual(len(mail.outbox), 0)

    def test_feil_i_transporten_gir_rad_med_feil_og_kaster_ikke(self):
        with override_settings(EMAIL_BACKEND='vaktliste.tests_fil.SviktendeBackend'):
            rad = fil.send_fil(self.vl, bruker=self.vaktleder)
        self.assertIn('nede', rad.feil)
        self.assertFalse(rad.gikk)
        audit = AuditLog.objects.get(table_name='vaktliste_utsending')
        self.assertIn('feilet', audit.new_value)

    def test_innstillingene_leses_som_liste_og_bryter(self):
        AppSetting.set(fil.MOTTAKERE_NOKKEL, ' a@example.org, b@example.org ;\nc@example.org\n\n')
        self.assertEqual(fil.mottakere(), ['a@example.org', 'b@example.org', 'c@example.org'])
        self.assertTrue(fil.sendes_ved_drift(), 'på som standard')
        AppSetting.set(fil.VED_DRIFT_NOKKEL, '0')
        self.assertFalse(fil.sendes_ved_drift())


class SviktendeBackend:
    """E-posttjeneste som er nede — for testen over."""

    def __init__(self, *a, **kw):
        pass

    def send_messages(self, meldinger):
        raise ConnectionError('AHASend er nede')


class EndepunktTests(FilBasis):
    def test_nedlasting_krever_skriv_full(self):
        self._skift(self.res_hgsd, self.p_hgsd)
        url = f'/vaktliste/api/vaktlister/{self.vl.pk}/fil/'
        for c in (self.c_leser, self.c_kb):
            self.assertEqual(c.get(url).status_code, 403)
        res = self.c_vl.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertIn('attachment; filename="vaktliste-', res['Content-Disposition'])
        self.assertIn('Kari', res.content.decode())
        self.assertEqual(Utsending.objects.count(), 0, 'nedlasting er ingen utlevering')

    def test_send_paa_knapp(self):
        self._skift(self.res_hgsd, self.p_hgsd)
        url = f'/vaktliste/api/vaktlister/{self.vl.pk}/fil/send/'
        self.assertEqual(self.c_kb.post(url).status_code, 403)
        res = self.c_vl.post(url)
        self.assertEqual(res.status_code, 200, res.content)
        d = res.json()['data']
        self.assertEqual(d['utloest'], 'knapp')
        self.assertEqual(d['antall_mottakere'], 2)
        self.assertEqual(len(mail.outbox), 1)
        detalj = self.c_vl.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/').json()['data']['vaktliste']
        self.assertEqual(detalj['siste_utsending']['id'], d['id'])
        self.assertEqual(detalj['fil_mottakere'], 2)
        self.assertTrue(detalj['fil_ved_drift'])

    def test_send_uten_mottakere_er_400_med_veiviser(self):
        AppSetting.set(fil.MOTTAKERE_NOKKEL, '')
        res = self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/fil/send/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Portalinnstillinger', res.json()['message'])
        self.assertEqual(len(mail.outbox), 0)

    def test_send_naar_transporten_svikter_er_502_med_rad(self):
        with override_settings(EMAIL_BACKEND='vaktliste.tests_fil.SviktendeBackend'):
            res = self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/fil/send/')
        self.assertEqual(res.status_code, 502)
        self.assertIn('nede', res.json()['message'])
        self.assertEqual(Utsending.objects.count(), 1)

    def test_sett_i_drift_sender_naar_admin_har_slaatt_det_paa(self):
        self._skift(self.res_hgsd, self.p_hgsd)
        res = self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/start/')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['utsending']['utloest'], 'drift')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Utsending.objects.get().utloest, Utsending.DRIFT)
        # Ut og inn igjen: ny utsending — lista kan ha endret seg.
        self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/stopp/')
        self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/start/')
        self.assertEqual(len(mail.outbox), 2)

    def test_sett_i_drift_sender_ikke_naar_det_er_av_eller_uten_mottakere(self):
        AppSetting.set(fil.VED_DRIFT_NOKKEL, '0')
        res = self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/start/')
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()['data']['utsending'])
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Utsending.objects.count(), 0, 'ingen rad når ingenting ble forsøkt')
        AppSetting.set(fil.VED_DRIFT_NOKKEL, '1')
        AppSetting.set(fil.MOTTAKERE_NOKKEL, '')
        self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/stopp/')
        self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/start/')
        self.assertEqual(Utsending.objects.count(), 0)

    def test_sett_i_drift_gaar_selv_om_e_posten_feiler(self):
        """En e-posttjeneste som er nede skal ikke hindre at innsjekken
        åpner. Svaret bærer feilen, så vaktleder får vite det nå."""
        with override_settings(EMAIL_BACKEND='vaktliste.tests_fil.SviktendeBackend'):
            res = self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/start/')
        self.assertEqual(res.status_code, 200, res.content)
        self.vl.refresh_from_db()
        self.assertTrue(self.vl.i_drift)
        self.assertIn('nede', res.json()['data']['utsending']['feil'])


class PortalinnstillingeneTests(FilBasis):
    def setUp(self):
        super().setUp()
        self.adm = _klient(_bruker('ps_adm', admin=True))
        self.kropp = {'event_name': self.vl.vakt.navn, 'session_timeout_hours': '8'}

    def test_mottakere_og_bryter_lagres(self):
        res = self.adm.post('/portal-admin/innstillinger/', {
            **self.kropp, 'vaktliste_fil_mottakere': 'x@example.org\n y@example.org '})
        self.assertEqual(res.status_code, 302, res.content)
        self.assertEqual(fil.mottakere(), ['x@example.org', 'y@example.org'])
        self.assertFalse(fil.sendes_ved_drift(), 'avkryssingen manglet: av')
        self.adm.post('/portal-admin/innstillinger/', {
            **self.kropp, 'vaktliste_fil_mottakere': '', 'vaktliste_fil_ved_drift': '1'})
        self.assertEqual(fil.mottakere(), [])
        self.assertTrue(fil.sendes_ved_drift())

    def test_ugyldig_adresse_avvises_uten_aa_lagre_halve_skjemaet(self):
        res = self.adm.post('/portal-admin/innstillinger/', {
            **self.kropp, 'session_timeout_hours': '5',
            'vaktliste_fil_mottakere': 'x@example.org\nikke en adresse'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('ikke en adresse', res.content.decode())
        self.assertEqual(fil.mottakere(), ['vaktleder@example.org', 'ko@example.org'], 'uendret')
        self.assertEqual(AppSetting.get('session_timeout_hours', '8'), '8', 'timeouten heller ikke')

    def test_siden_viser_det_som_er_satt(self):
        html = self.adm.get('/portal-admin/innstillinger/').content.decode()
        self.assertIn('vaktleder@example.org\nko@example.org', html)
        self.assertIn('id="vaktliste_fil_ved_drift"', html)
        self.assertIn('checked', html)


class FilknappeneJsTests(SimpleTestCase):
    """Knappene i «Innstillinger»: for `skriv_full`, og teksten sier om det
    finnes mottakere og hva som skjedde sist."""
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('tegnFilknapper', '_utsendingTekst', '_dag', '_kl', '_d')),
    )
    STUBB = ("globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun','jul','aug','sep','okt','nov','des'];\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = self.STUBB + build_harness(self.HARNESS)

    def _kjor(self, vaktliste, kan_skrive='true'):
        return run_node(self.harness, f"""
            const el = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: (id) => id === 'vl-fil' ? el : null }};
            globalThis.kanSkriveAlt = () => {kan_skrive};
            globalThis.aktivListe = {{ vaktliste: {json.dumps(vaktliste)} }};
            tegnFilknapper();
            console.log(el.innerHTML);
        """)

    def test_bare_for_skriv_full(self):
        # `run_node` legger på «OK» sist; et tomt panel gir bare den linja.
        self.assertEqual(self._kjor({'id': 1, 'fil_mottakere': 2}, 'false').strip(), 'OK')

    def test_knappene_og_teksten(self):
        ut = self._kjor({'id': 7, 'fil_mottakere': 2, 'fil_ved_drift': True, 'siste_utsending': None})
        self.assertIn('/vaktliste/api/vaktlister/7/fil/', ut)
        self.assertIn('data-action="sendVaktlistefil"', ut)
        self.assertNotIn('disabled', ut)
        self.assertIn('2 mottakere er satt; sendes også ved sett i drift.', ut)

    def test_uten_mottakere_er_sending_slaatt_av_og_teksten_sier_hvor(self):
        ut = self._kjor({'id': 7, 'fil_mottakere': 0, 'fil_ved_drift': True})
        self.assertIn('disabled', ut)
        self.assertIn('Portalinnstillinger', ut)

    def test_siste_utsending_vises_med_feil_naar_den_feilet(self):
        ok = {'sendt_at': '2026-09-12T06:04:00Z', 'utloest': 'drift', 'antall_mottakere': 1,
              'antall_rader': 12, 'feil': ''}
        ut = self._kjor({'id': 7, 'fil_mottakere': 1, 'siste_utsending': ok})
        self.assertIn('Sist sendt', ut)
        self.assertIn('til 1 mottaker (ved sett i drift), 12 skift.', ut)
        feilet = {**ok, 'utloest': 'knapp', 'feil': '<b>nede</b>'}
        ut = self._kjor({'id': 7, 'fil_mottakere': 1, 'siste_utsending': feilet})
        self.assertIn('feilet: &lt;b&gt;nede&lt;/b&gt;', ut)
        self.assertNotIn('<b>nede', ut)


class IntervallTests(FilBasis):
    """«En intervall på sending av epost og checkbox, mail sendes bare hvis
    det er endringer i vaktlisten» (André, 13. sep. 2026)."""

    def setUp(self):
        super().setUp()
        AppSetting.set(fil.INTERVALL_NOKKEL, '5')
        self._skift(self.res_hgsd, self.p_hgsd)
        self.vl.status = 'drift'
        self.vl.save()

    def _sist(self, minutter):
        """Flytt den siste utsendingen `minutter` tilbake i tid."""
        rad = self.vl.utsendinger.first()
        Utsending.objects.filter(pk=rad.pk).update(created_at=timezone.now() - timedelta(minutes=minutter))
        return rad

    def test_av_naar_intervallet_er_null_eller_lista_ikke_er_i_drift(self):
        AppSetting.set(fil.INTERVALL_NOKKEL, '0')
        self.assertEqual(fil.send_planlagte(), [])
        AppSetting.set(fil.INTERVALL_NOKKEL, '5')
        self.vl.status = 'planlegging'
        self.vl.save()
        self.assertEqual(fil.send_planlagte(), [])
        self.assertEqual(len(mail.outbox), 0)

    def test_forste_sending_i_drift_uten_tidligere_utsending(self):
        rader = fil.send_planlagte()
        self.assertEqual(len(rader), 1)
        self.assertEqual(rader[0].utloest, Utsending.INTERVALL)
        self.assertEqual(rader[0].sendt_av, None)
        self.assertTrue(rader[0].innhold_sha256)
        self.assertEqual(len(mail.outbox), 1)

    def test_venter_til_intervallet_er_gaatt(self):
        fil.send_fil(self.vl, bruker=self.vaktleder)
        self._sist(4)
        self.assertEqual(fil.send_planlagte(), [], 'fire minutter: for tidlig')
        self._sist(5)
        AppSetting.set(fil.BARE_ENDRET_NOKKEL, '0')
        self.assertEqual(len(fil.send_planlagte()), 1)

    def test_bare_ved_endring_hopper_over_uendret_liste(self):
        fil.send_fil(self.vl, bruker=self.vaktleder)
        self._sist(6)
        self.assertEqual(fil.send_planlagte(), [], 'uendret: ingenting sendes, ingen rad')
        self.assertEqual(Utsending.objects.count(), 1)
        self._skift(self.res_karmoy, self.p_karmoy, fra=8, til=16)
        rader = fil.send_planlagte()
        self.assertEqual(len(rader), 1, 'endret: sendes')
        self.assertNotEqual(rader[0].innhold_sha256, Utsending.objects.order_by('pk').first().innhold_sha256)
        self.assertEqual(len(mail.outbox), 2)

    def test_uten_bare_ved_endring_sendes_uendret_liste(self):
        AppSetting.set(fil.BARE_ENDRET_NOKKEL, '0')
        fil.send_fil(self.vl, bruker=self.vaktleder)
        self._sist(6)
        self.assertEqual(len(fil.send_planlagte()), 1)

    def test_et_feilet_forsoek_teller_som_forrige(self):
        """E-posttjenesten nede: ett forsøk per intervall, ikke ett per
        minutt. Og sammenligningen går mot den sist *sendte*, så en endring
        som feilet første gang går ut når tjenesten er oppe igjen."""
        fil.send_fil(self.vl, bruker=self.vaktleder)
        self._sist(6)
        self._skift(self.res_karmoy, self.p_karmoy, fra=8, til=16)
        with override_settings(EMAIL_BACKEND='vaktliste.tests_fil.SviktendeBackend'):
            feilet = fil.send_planlagte()
        self.assertEqual(len(feilet), 1)
        self.assertTrue(feilet[0].feil)
        self.assertEqual(fil.send_planlagte(), [], 'nytt forsøk først etter intervallet')
        self._sist(6)
        rader = fil.send_planlagte()
        self.assertEqual(len(rader), 1)
        self.assertEqual(rader[0].feil, '')

    def test_stempling_er_en_endring(self):
        fil.send_fil(self.vl, bruker=self.vaktleder)
        self._sist(6)
        self.assertEqual(fil.send_planlagte(), [])
        vp = self.vl.ressurser.get(navn='Lag HGSD').vaktposter.get()
        # Stemplene står ikke i fila, og skal ikke utløse en ny utsending —
        # fila er planen, ikke innsjekken.
        vp.mott_at = timezone.now()
        vp.save()
        self.assertEqual(fil.send_planlagte(), [], 'møtt endrer ikke fila')
        vp.til_tid = vp.til_tid + timedelta(hours=1)
        vp.save()
        self.assertEqual(len(fil.send_planlagte()), 1, 'en ny til-tid gjør det')


class FilutsendingMiddlewareTests(FilBasis):
    def setUp(self):
        super().setUp()
        from . import middleware
        middleware.nullstill_for_test()

    def tearDown(self):
        from . import middleware
        middleware.nullstill_for_test()
        super().tearDown()

    def test_maks_en_sjekk_per_minutt(self):
        from unittest.mock import patch
        from . import middleware
        with patch.object(middleware.threading, 'Thread') as Thread:
            self.assertTrue(middleware.maybe_send_planlagte())
            self.assertFalse(middleware.maybe_send_planlagte(), 'throttlet')
            Thread.return_value.start.assert_called_once()

    def test_traaden_kaller_send_planlagte_og_slipper_laasen(self):
        from unittest.mock import patch
        from . import middleware
        with patch.object(fil, 'send_planlagte', return_value=[]) as sp:
            middleware._kjor()
            sp.assert_called_once()
        self.assertFalse(middleware._kjorer)
        with patch.object(fil, 'send_planlagte', side_effect=RuntimeError('boom')):
            middleware._kjor()      # kaster ikke
        self.assertFalse(middleware._kjorer)

    def test_middlewaren_er_registrert_men_ikke_under_test(self):
        from django.conf import settings as s
        self.assertNotIn('vaktliste.middleware.FilutsendingMiddleware', s.MIDDLEWARE,
                         'tas ut under test, som backup-planleggeren')
        from pathlib import Path
        kilde = (Path(s.BASE_DIR) / 'myproject' / 'settings.py').read_text(encoding='utf-8')
        self.assertIn("'vaktliste.middleware.FilutsendingMiddleware',\n", kilde)


class IntervallInnstillingeneTests(FilBasis):
    def setUp(self):
        super().setUp()
        self.adm = _klient(_bruker('ps_adm2', admin=True))
        self.kropp = {'event_name': self.vl.vakt.navn, 'session_timeout_hours': '8',
                      'vaktliste_fil_mottakere': 'x@example.org'}

    def test_intervall_og_bryter_lagres(self):
        res = self.adm.post('/portal-admin/innstillinger/', {
            **self.kropp, 'vaktliste_fil_intervall_min': '5', 'vaktliste_fil_bare_endret': '1'})
        self.assertEqual(res.status_code, 302, res.content)
        self.assertEqual(fil.intervall_minutter(), 5)
        self.assertTrue(fil.bare_ved_endring())
        res = self.adm.post('/portal-admin/innstillinger/', {**self.kropp, 'vaktliste_fil_intervall_min': ''})
        self.assertEqual(res.status_code, 302)
        self.assertEqual(fil.intervall_minutter(), 0, 'tomt = av')
        self.assertFalse(fil.bare_ved_endring())

    def test_ugyldig_intervall_avvises_uten_aa_lagre(self):
        AppSetting.set(fil.INTERVALL_NOKKEL, '5')
        for verdi in ('-1', 'fem', '9999'):
            with self.subTest(verdi=verdi):
                res = self.adm.post('/portal-admin/innstillinger/', {
                    **self.kropp, 'session_timeout_hours': '3', 'vaktliste_fil_intervall_min': verdi})
                self.assertEqual(res.status_code, 200)
                self.assertEqual(fil.intervall_minutter(), 5)
                self.assertEqual(AppSetting.get('session_timeout_hours', '8'), '8', 'halve skjemaet lagres ikke')

    def test_teksten_i_innstillinger_sier_intervallet(self):
        AppSetting.set(fil.INTERVALL_NOKKEL, '5')
        d = self.c_vl.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/').json()['data']['vaktliste']
        self.assertEqual((d['fil_intervall_min'], d['fil_bare_endret']), (5, True))


class IntervallTekstJsTests(FilknappeneJsTests):
    def test_teksten_nevner_intervallet_og_endringskravet(self):
        ut = self._kjor({'id': 7, 'fil_mottakere': 1, 'fil_ved_drift': True,
                         'fil_intervall_min': 5, 'fil_bare_endret': True})
        self.assertIn('sendes også ved sett i drift og hvert 5. min i drift når lista er endret.', ut)
        ut = self._kjor({'id': 7, 'fil_mottakere': 1, 'fil_ved_drift': False,
                         'fil_intervall_min': 10, 'fil_bare_endret': False})
        self.assertIn('sendes også hvert 10. min i drift.', ut)
        ut = self._kjor({'id': 7, 'fil_mottakere': 1, 'siste_utsending': {
            'sendt_at': '2026-09-13T06:04:00Z', 'utloest': 'intervall', 'antall_mottakere': 1,
            'antall_rader': 3, 'feil': ''}})
        self.assertIn('(på intervall)', ut)
