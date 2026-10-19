"""Hodet i hendelsen (19. okt. 2026): beskrivelsen står fast og kan oppdateres,
de eksterne aktørene krysses av som varslet, og melderen og varslingene
følger oppdraget ut til sentralbordet og bilen.

André: «Beskrivelse av hendelse: Kunne oppdatere hendelse. Samt at
beskrivelsen står som fast oversikt i hendelsen. Tidskritisk informasjon»,
«Andre Ressurser: Legge inn andre eksterne ressurser, samt avkryssing på om
og når de er varslet … Automatisk loggføres og deles til aktuelle ressurser»
og «hendelser som varslet av AMK. Må komme frem i hendelsen og oppdraget».

Tyngden ligger i tjenestelaget (`CLAUDE.md`, «Mutasjonstesting»): en feil i
`sett_beskrivelse` eller `varsle` legger seg i data og sees av ingen. Portene
prøves som porter. Markupen prøves i node nederst, gjennom de ekte byggerne.
"""
from __future__ import annotations

import importlib
import json
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core import endringer
from core.vakt import hent_aktiv_vakt
from ko import services
from ko.models import KILDE_OPERATOR, EksternRessurs, Hendelse, HendelseVarsling, Logglinje, Talegruppe
from ko.tests_hendelseslogg import _bruker, _gi
from oppdrag import choices
from oppdrag.models import Enhet, Lokasjon
from oppdrag.test_helpers import lag_oppdrag
from oppdrag.views_common import oppdrag_til_dict


class _Grunnlag(TestCase):

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.kari = _gi(_bruker('kari'), 'ko', 'skriv_full')
        self.per = _gi(_bruker('per'), 'ko', 'skriv_full')
        self.brann, _ = EksternRessurs.objects.get_or_create(navn='Brann')
        self.politi, _ = EksternRessurs.objects.get_or_create(navn='Politi')

    def _hendelse(self, **kw):
        return services.opprett_hendelse(self.vakt, 'Brann i telt', bruker=self.kari, **kw)

    def _oppdrag(self, h):
        _gi(self.kari, 'oppdrag', 'skriv_full')
        o = lag_oppdrag(vakt=self.vakt, oppdragsnummer=1,
                        enhet=Enhet.objects.create(navn='HGSD 56', pa_vakt=True),
                        lokasjon=Lokasjon.objects.create(navn='Scene'),
                        problemstilling='Fall', hastegrad=choices.HASTEGRAD[0])
        services.knytt_oppdrag(o, h, bruker=self.kari)
        return o


class BeskrivelsenTests(_Grunnlag):
    """En logglinje, pekt på av hodet; en oppdatering er en retting."""

    def test_opprettelsen_setter_pekeren_til_linja(self):
        h = self._hendelse(beskrivelse='Røyk fra telt B')
        linje = Logglinje.objects.get(hendelse=h, kilde=KILDE_OPERATOR)
        h.refresh_from_db()
        self.assertEqual(h.beskrivelse_linje_id, linje.pk)
        self.assertIsNone(self._hendelse().beskrivelse_linje_id, 'uten beskrivelse, ingen peker')

    def test_uten_beskrivelse_blir_det_en_ny_intern_linje(self):
        h = self._hendelse()
        ny = services.sett_beskrivelse(h, 'Røyk', bruker=self.per)
        h.refresh_from_db()
        self.assertEqual(h.beskrivelse_linje_id, ny.pk)
        self.assertEqual((ny.hendelse_id, ny.tekst, ny.forfatter_navn, ny.delt_at),
                         (h.pk, 'Røyk', 'per', None))
        self.assertIn('per', list(h.deltakere.values_list('brukernavn', flat=True)))

    def test_oppdatering_er_en_retting_og_pekeren_staar_paa_roten(self):
        h = self._hendelse(beskrivelse='v1')
        rot = h.beskrivelse_linje
        v2 = services.sett_beskrivelse(h, 'v2', bruker=self.per)
        v3 = services.sett_beskrivelse(h, 'v3', bruker=self.kari)
        h.refresh_from_db()
        self.assertEqual(h.beskrivelse_linje_id, rot.pk, 'roten endres aldri')
        self.assertEqual((v2.korrigerer_id, v2.rot_id), (rot.pk, rot.pk))
        self.assertEqual((v3.korrigerer_id, v3.rot_id), (v2.pk, rot.pk))
        self.assertEqual(services.gjeldende_i_kjeden(rot).pk, v3.pk)
        self.assertEqual(Logglinje.objects.filter(hendelse=h).filter(pk__in=[rot.pk, v2.pk]).count(), 2,
                         'det som sto før kan leses')
        self.assertIn('per', list(h.deltakere.values_list('brukernavn', flat=True)))

    def test_en_utdatert_versjon_er_konflikt_ikke_overskriving(self):
        h = self._hendelse(beskrivelse='v1')
        rot = h.beskrivelse_linje
        v2 = services.sett_beskrivelse(h, 'v2', bruker=self.per, sett_linje=rot.pk)
        with self.assertRaises(services.AlleredeKorrigert):
            services.sett_beskrivelse(h, 'kari sin', bruker=self.kari, sett_linje=rot.pk)
        self.assertEqual(services.gjeldende_i_kjeden(rot).pk, v2.pk)
        v3 = services.sett_beskrivelse(h, 'v3', bruker=self.kari, sett_linje=str(v2.pk))
        self.assertEqual(v3.korrigerer_id, v2.pk, 'riktig versjon, også som tekst fra JSON')

    def test_tom_og_for_lang_avvises(self):
        h = self._hendelse(beskrivelse='v1')
        for tekst in ('', '   ', None, 'x' * (services.MAKS_BESKRIVELSE + 1)):
            with self.subTest(tekst=tekst), self.assertRaisesRegex(services.Ugyldig, 'Beskrivelsen'):
                services.sett_beskrivelse(h, tekst, bruker=self.kari)
        self.assertEqual(Logglinje.objects.filter(hendelse=h, kilde=KILDE_OPERATOR).count(), 1)

    def test_fjernet_beskrivelse_gir_ny_linje_og_ny_peker(self):
        h = self._hendelse(beskrivelse='helseopplysning')
        gammel = h.beskrivelse_linje
        services.fjern(gammel, bruker=self.kari)
        ny = services.sett_beskrivelse(h, 'Ny tekst', bruker=self.kari)
        h.refresh_from_db()
        self.assertEqual(h.beskrivelse_linje_id, ny.pk)
        self.assertIsNone(ny.korrigerer_id)

    def test_en_delt_beskrivelse_forblir_delt_og_bilen_ser_den_nye(self):
        h = self._hendelse(beskrivelse='Røyk')
        o = self._oppdrag(h)
        services.del_linje(h.beskrivelse_linje, bruker=self.kari)
        services.sett_beskrivelse(h, 'Åpen flamme', bruker=self.kari)
        self.assertEqual([t['tekst'] for t in oppdrag_til_dict(o, for_enhet=True)['delte_linjer']],
                         ['Åpen flamme'])


class VarslingTests(_Grunnlag):
    """Raden er tilstanden; linja er det loggen og bilene ser."""

    def test_varsling_skriver_en_delt_operatorlinje_og_en_rad(self):
        h = self._hendelse()
        o = self._oppdrag(h)
        tid = timezone.now() - timedelta(minutes=5)
        v = services.varsle(h, self.brann, bruker=self.per, tidspunkt=tid)
        self.assertEqual((v.navn, v.varslet_at, v.av_navn, v.ressurs_id), ('Brann', tid, 'per', self.brann.pk))
        linje = v.linje
        self.assertEqual((linje.kilde, linje.tekst, linje.tidspunkt, linje.hendelse_id, linje.forfatter_navn),
                         (KILDE_OPERATOR, 'Varslet Brann', tid, h.pk, 'per'))
        self.assertIsNotNone(linje.delt_at, 'delt automatisk')
        self.assertEqual([t['tekst'] for t in oppdrag_til_dict(o, for_enhet=True)['delte_linjer']],
                         ['Varslet Brann'])
        self.assertIn('per', list(h.deltakere.values_list('brukernavn', flat=True)))

    def test_to_avkryssinger_gir_en_rad_og_en_linje(self):
        h = self._hendelse()
        forste = services.varsle(h, self.brann, bruker=self.kari)
        andre = services.varsle(h, self.brann, bruker=self.per)
        self.assertEqual(forste.pk, andre.pk)
        self.assertEqual(Logglinje.objects.filter(hendelse=h, kilde=KILDE_OPERATOR).count(), 1)
        self.assertEqual(andre.av_navn, 'kari', 'den første avkryssingen står')

    def test_lukket_inaktiv_og_ukjent_avvises_uten_spor(self):
        h = self._hendelse()
        self.politi.er_aktiv = False
        self.politi.save()
        for ressurs in (self.politi, None):
            with self.subTest(ressurs=ressurs), self.assertRaises(services.Ugyldig):
                services.varsle(h, ressurs, bruker=self.kari)
        services.lukk_hendelse(h, bruker=self.kari)
        with self.assertRaises(services.Ugyldig):
            services.varsle(h, self.brann, bruker=self.kari)
        self.assertFalse(HendelseVarsling.objects.exists())
        self.assertFalse(Logglinje.objects.filter(hendelse=h, kilde=KILDE_OPERATOR).exists())

    def test_tid_utenfor_vinduet_avvises_for_noe_skrives(self):
        h = self._hendelse()
        with self.assertRaises(services.Ugyldig):
            services.varsle(h, self.brann, bruker=self.kari, tidspunkt=timezone.now() - timedelta(days=2))
        self.assertFalse(HendelseVarsling.objects.exists())

    def test_angring_sletter_raden_og_retter_linja_som_forblir_delt(self):
        h = self._hendelse()
        o = self._oppdrag(h)
        v = services.varsle(h, self.brann, bruker=self.kari)
        self.assertTrue(services.angre_varsling(h, self.brann.pk, bruker=self.per))
        self.assertFalse(HendelseVarsling.objects.exists())
        gjeldende = services.gjeldende_i_kjeden(v.linje)
        self.assertEqual((gjeldende.tekst, gjeldende.korrigerer_id), ('Varsling av Brann angret', v.linje.pk))
        self.assertIsNotNone(gjeldende.delt_at, 'bilen som så «Varslet» skal se angringen')
        self.assertEqual([t['tekst'] for t in oppdrag_til_dict(o, for_enhet=True)['delte_linjer']],
                         ['Varsling av Brann angret'])
        self.assertFalse(services.angre_varsling(h, self.brann.pk, bruker=self.per), 'ingenting å angre')

    def test_angring_paa_lukket_avvises(self):
        h = self._hendelse()
        services.varsle(h, self.brann, bruker=self.kari)
        services.lukk_hendelse(h, bruker=self.kari)
        with self.assertRaises(services.Ugyldig):
            services.angre_varsling(h, self.brann.pk, bruker=self.kari)
        self.assertTrue(HendelseVarsling.objects.exists())

    def test_ny_avkryssing_etter_angring_er_en_ny_varsling(self):
        h = self._hendelse()
        services.varsle(h, self.brann, bruker=self.kari)
        services.angre_varsling(h, self.brann.pk, bruker=self.kari)
        services.varsle(h, self.brann, bruker=self.kari)
        self.assertEqual(HendelseVarsling.objects.count(), 1)
        # Den første «Varslet Brann» står i kjeden bak angringen; gjeldende er én.
        self.assertEqual(Logglinje.objects.filter(hendelse=h, tekst='Varslet Brann',
                                                  korrigert_av__isnull=True).count(), 1)

    def test_varslingen_oker_endringsnummeret_til_sentralbordet_og_loggen(self):
        """Raden står på oppdraget (`hendelse_varslet`) og i hodet; uten
        tallet ser sentralbordet og bilen den først ved sikkerhetsnettet.
        Tallet øker ved commit, derfor `captureOnCommitCallbacks`."""
        h = self._hendelse()
        for handling in ('lagre', 'slette'):
            foer = {o: endringer.versjon(o) for o in ('oppdrag', 'logg')}
            with self.captureOnCommitCallbacks(execute=True):
                if handling == 'lagre':
                    HendelseVarsling.objects.create(hendelse=h, ressurs=self.politi, navn='Politi',
                                                    varslet_at=timezone.now())
                else:
                    HendelseVarsling.objects.filter(ressurs=self.politi).delete()
            for omraade, tall in foer.items():
                with self.subTest(handling=handling, omraade=omraade):
                    self.assertNotEqual(endringer.versjon(omraade), tall)


class OppdragetTests(_Grunnlag):
    """«Må komme frem i hendelsen og oppdraget» — melderen og varslingene."""

    def test_melder_og_varslede_staar_paa_oppdraget(self):
        h = self._hendelse(melder_typer=['amk', 'politi'])
        o = self._oppdrag(h)
        tid = timezone.now() - timedelta(minutes=3)
        services.varsle(h, self.politi, bruker=self.kari, tidspunkt=tid)
        services.varsle(h, self.brann, bruker=self.kari)
        for for_enhet in (False, True):
            with self.subTest(for_enhet=for_enhet):
                d = oppdrag_til_dict(o, for_enhet=for_enhet)
                self.assertEqual(d['hendelse_melder'], 'AMK, Politi')
                self.assertEqual([v['navn'] for v in d['hendelse_varslet']], ['Politi', 'Brann'],
                                 'i den rekkefølgen de ble varslet')
                self.assertEqual(d['hendelse_varslet'][0]['tid'], tid.isoformat())

    def test_uten_hendelse_er_feltene_tomme(self):
        h = self._hendelse()
        o = self._oppdrag(h)
        o.hendelse = None
        o.save()
        d = oppdrag_til_dict(o)
        self.assertEqual((d['hendelse_melder'], d['hendelse_varslet']), ('', []))

    def test_listene_henter_varslingene_i_en_spørring(self):
        """Lista polles; en spørring per oppdrag er det G4 fjernet."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        _gi(self.kari, 'oppdrag', 'skriv_full')
        c = Client()
        c.force_login(self.kari)
        h = self._hendelse()
        self._oppdrag(h)
        services.varsle(h, self.brann, bruker=self.kari)
        with self.settings(SECURE_SSL_REDIRECT=False), CaptureQueriesContext(connection) as en:
            c.get('/oppdrag/api/oppdrag/')
        for n in range(2, 5):
            o = lag_oppdrag(vakt=self.vakt, oppdragsnummer=n, enhet=None,
                            lokasjon=Lokasjon.objects.create(navn=f'S{n}'),
                            problemstilling='Fall', hastegrad=choices.HASTEGRAD[0])
            services.knytt_oppdrag(o, h, bruker=self.kari)
        with self.settings(SECURE_SSL_REDIRECT=False), CaptureQueriesContext(connection) as fire:
            svar = c.get('/oppdrag/api/oppdrag/')
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(len(en), len(fire))


class TalegruppeTests(_Grunnlag):
    """TG i Nødnett (André, 19. okt. 2026): fra lista, en linje per endring,
    og bilene ser den bare når den er delt."""

    def setUp(self):
        super().setUp()
        Talegruppe.objects.get_or_create(navn='SAMVIRKE 2')
        Talegruppe.objects.get_or_create(navn='SAMVIRKE 3')

    def _tg_linjer(self, h):
        return list(Logglinje.objects.filter(hendelse=h, kilde=KILDE_OPERATOR, tekst__startswith='TG')
                    .order_by('id').values_list('tekst', 'delt_at'))

    def test_intern_tg_er_en_intern_linje_og_bilen_ser_den_ikke(self):
        h = self._hendelse()
        o = self._oppdrag(h)
        services.sett_talegruppe(h, 'SAMVIRKE 2', bruker=self.per)
        h.refresh_from_db()
        self.assertEqual((h.talegruppe, h.talegruppe_delt), ('SAMVIRKE 2', False))
        self.assertEqual([t for t, _ in self._tg_linjer(h)], ['TG: SAMVIRKE 2'])
        self.assertIsNone(self._tg_linjer(h)[0][1], 'intern')
        self.assertEqual(oppdrag_til_dict(o, for_enhet=True)['hendelse_talegruppe'], '')
        self.assertEqual(oppdrag_til_dict(o)['hendelse_talegruppe'], 'SAMVIRKE 2', 'sentralbordet ser den')
        self.assertIn('per', list(h.deltakere.values_list('brukernavn', flat=True)))

    def test_delt_tg_naar_bilen_som_felt_og_linje(self):
        h = self._hendelse()
        o = self._oppdrag(h)
        services.sett_talegruppe(h, 'SAMVIRKE 2', bruker=self.per, del_med_enhetene=True)
        d = oppdrag_til_dict(o, for_enhet=True)
        self.assertEqual(d['hendelse_talegruppe'], 'SAMVIRKE 2')
        self.assertEqual([t['tekst'] for t in d['delte_linjer']], ['TG: SAMVIRKE 2'])

    def test_uendret_gir_ingen_linje_men_ny_deling_gjor(self):
        h = self._hendelse()
        services.sett_talegruppe(h, 'SAMVIRKE 2', bruker=self.per)
        services.sett_talegruppe(h, 'SAMVIRKE 2', bruker=self.per)
        self.assertEqual(len(self._tg_linjer(h)), 1)
        services.sett_talegruppe(h, 'SAMVIRKE 2', bruker=self.per, del_med_enhetene=True)
        linjer = self._tg_linjer(h)
        self.assertEqual(len(linjer), 2)
        self.assertIsNotNone(linjer[-1][1], 'nå delt')

    def test_fjerning_av_en_delt_tg_deles_ogsaa(self):
        h = self._hendelse()
        o = self._oppdrag(h)
        services.sett_talegruppe(h, 'SAMVIRKE 2', bruker=self.per, del_med_enhetene=True)
        # «Sett og del» med «— ingen TG —» valgt: en tom TG er aldri «delt».
        services.sett_talegruppe(h, '', bruker=self.per, del_med_enhetene=True)
        h.refresh_from_db()
        self.assertEqual((h.talegruppe, h.talegruppe_delt), ('', False))
        self.assertIsNotNone(self._tg_linjer(h)[-1][1], 'bilen skal se at den ikke gjelder lenger')
        self.assertEqual([t['tekst'] for t in oppdrag_til_dict(o, for_enhet=True)['delte_linjer']],
                         ['TG: SAMVIRKE 2', 'TG fjernet'])
        h2 = self._hendelse()
        services.sett_talegruppe(h2, 'SAMVIRKE 3', bruker=self.per)
        services.sett_talegruppe(h2, '', bruker=self.per)
        self.assertIsNone(self._tg_linjer(h2)[-1][1], 'en intern TG fjernes internt')

    def test_ukjent_inaktiv_annen_portal_og_lukket_avvises(self):
        from core.models import Vaktportal
        annen = Vaktportal.objects.create(navn='Brannkorpset', slug='brannkorpset')
        Talegruppe.objects.create(navn='FREMMED', portal=annen)
        Talegruppe.objects.filter(navn='SAMVIRKE 3').update(er_aktiv=False)
        h = self._hendelse()
        for navn in ('TULL', 'SAMVIRKE 3', 'FREMMED'):
            with self.subTest(navn=navn), self.assertRaises(services.Ugyldig):
                services.sett_talegruppe(h, navn, bruker=self.per)
        services.lukk_hendelse(h, bruker=self.per)
        with self.assertRaises(services.Ugyldig):
            services.sett_talegruppe(h, 'SAMVIRKE 2', bruker=self.per)
        self.assertEqual(self._tg_linjer(h), [])

    def test_en_deaktivert_tg_kan_beholdes_naar_bare_delingen_endres(self):
        h = self._hendelse()
        services.sett_talegruppe(h, 'SAMVIRKE 3', bruker=self.per)
        Talegruppe.objects.filter(navn='SAMVIRKE 3').update(er_aktiv=False)
        services.sett_talegruppe(h, 'SAMVIRKE 3', bruker=self.per, del_med_enhetene=True)
        h.refresh_from_db()
        self.assertTrue(h.talegruppe_delt)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(_Grunnlag):

    def setUp(self):
        super().setUp()
        self.leser = _gi(_bruker('leser'), 'ko', 'les')

    def _post(self, bruker, sti, kropp=None):
        c = Client()
        c.force_login(bruker)
        return c.post(sti, data=json.dumps(kropp or {}), content_type='application/json')

    def test_beskrivelsen_krever_skriv_full_og_svarer_med_linja(self):
        h = self._hendelse(beskrivelse='v1')
        sti = f'/ko/api/hendelser/{h.pk}/beskrivelse/'
        self.assertEqual(self._post(self.leser, sti, {'tekst': 'x'}).status_code, 403)
        svar = self._post(self.per, sti, {'tekst': 'v2', 'linje': h.beskrivelse_linje_id})
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertEqual(svar.json()['linje']['tekst'], 'v2')
        self.assertEqual(svar.json()['data']['beskrivelse_rot'], h.beskrivelse_linje_id)
        self.assertEqual(self._post(self.per, sti, {'tekst': 'v3', 'linje': h.beskrivelse_linje_id}).status_code,
                         409, 'utdatert versjon')
        self.assertEqual(self._post(self.per, sti, {'tekst': ''}).status_code, 400)

    def test_varslingen_krever_skriv_full_og_svarer_med_hodet(self):
        h = self._hendelse()
        sti = f'/ko/api/hendelser/{h.pk}/varsling/'
        self.assertEqual(self._post(self.leser, sti, {'ressurs_id': self.brann.pk}).status_code, 403)
        self.assertFalse(HendelseVarsling.objects.exists())
        svar = self._post(self.per, sti, {'ressurs_id': self.brann.pk, 'varslet': True})
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertEqual([(v['ressurs_id'], v['navn'], v['av']) for v in svar.json()['data']['varslinger']],
                         [(self.brann.pk, 'Brann', 'per')])
        svar = self._post(self.per, sti, {'ressurs_id': self.brann.pk, 'varslet': False})
        self.assertEqual(svar.json()['data']['varslinger'], [])
        self.assertEqual(self._post(self.per, sti, {'ressurs_id': 'x'}).status_code, 400)
        self.assertEqual(self._post(self.per, sti, {'ressurs_id': 99999}).status_code, 400)

    def test_en_aktor_fra_en_annen_portal_er_ukjent(self):
        from core.models import Vaktportal
        annen = Vaktportal.objects.create(navn='Brannkorpset', slug='brannkorpset')
        fremmed = EksternRessurs.objects.create(navn='Kystvakt', portal=annen)
        h = self._hendelse()
        svar = self._post(self.per, f'/ko/api/hendelser/{h.pk}/varsling/', {'ressurs_id': fremmed.pk})
        self.assertEqual(svar.status_code, 400)
        self.assertFalse(HendelseVarsling.objects.exists())

    def test_hendelse_i_en_annen_vakt_er_404(self):
        from core.vakt import vakt_for_year
        h = self._hendelse()
        annen = vakt_for_year(2001, self.vakt.portal)
        Hendelse.objects.filter(pk=h.pk).update(vakt=annen)
        for sti, kropp in (('beskrivelse', {'tekst': 'x'}), ('varsling', {'ressurs_id': self.brann.pk})):
            with self.subTest(sti=sti):
                self.assertEqual(self._post(self.per, f'/ko/api/hendelser/{h.pk}/{sti}/', kropp).status_code, 404)

    def test_tg_krever_skriv_full_og_del_maa_vaere_sann(self):
        Talegruppe.objects.get_or_create(navn='SAMVIRKE 2')
        h = self._hendelse()
        sti = f'/ko/api/hendelser/{h.pk}/talegruppe/'
        self.assertEqual(self._post(self.leser, sti, {'talegruppe': 'SAMVIRKE 2'}).status_code, 403)
        svar = self._post(self.per, sti, {'talegruppe': 'SAMVIRKE 2', 'del': 'ja'})
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertEqual((svar.json()['data']['talegruppe'], svar.json()['data']['talegruppe_delt']),
                         ('SAMVIRKE 2', False), '«del» må være true, ikke bare noe')
        svar = self._post(self.per, sti, {'talegruppe': 'SAMVIRKE 2', 'del': True})
        self.assertTrue(svar.json()['data']['talegruppe_delt'])
        self.assertEqual(self._post(self.per, sti, {'talegruppe': 'TULL'}).status_code, 400)

    def test_tg_lista_settes_opp_av_ko_leder_moderator_og_admin(self):
        from accounts.models import PortalRolle, Portaltilgang
        sti = '/ko/api/talegrupper/'
        self.assertEqual(self._post(self.per, sti, {'navn': 'X1'}).status_code, 403, 'skriv_full holder ikke')
        moderator = _gi(_bruker('moderator'), 'ko', 'les')
        Portaltilgang.objects.update_or_create(bruker=moderator, portal=self.vakt.portal,
                                               defaults={'rolle': PortalRolle.MODERATOR})
        leder = _gi(_bruker('leder'), 'ko', 'skriv_leder')
        admin = _bruker('sjef', role='admin')
        for i, hvem in enumerate((moderator, leder, admin)):
            with self.subTest(hvem=hvem.username):
                svar = self._post(hvem, sti, {'navn': f'SAMVIRKE {i + 10}'})
                self.assertIn(svar.status_code, (200, 201), svar.content)
        self.assertEqual(self._post(moderator, '/ko/api/eksterne/', {'navn': 'Kystvakt'}).status_code, 403,
                         'moderator får TG-lista, ikke resten av KO-innstillingene')

    def test_tg_fanen_vises_for_moderator_alene(self):
        from accounts.models import PortalRolle, Portaltilgang
        moderator = _gi(_bruker('moderator'), 'ko', 'les')
        Portaltilgang.objects.update_or_create(bruker=moderator, portal=self.vakt.portal,
                                               defaults={'rolle': PortalRolle.MODERATOR})
        for hvem, ventet in ((self.per, []), (moderator, ['talegrupper'])):
            c = Client()
            c.force_login(hvem)
            faner = [f['slug'] for f in c.get('/ko/').context['verdifaner_ekstra']]
            with self.subTest(hvem=hvem.username):
                self.assertEqual(faner, ventet)

    def test_aktorlista_settes_opp_av_ko_leder(self):
        sti = '/ko/api/eksterne/'
        self.assertEqual(self._post(self.per, sti, {'navn': 'TG Samvirke'}).status_code, 403)
        leder = _gi(_bruker('leder'), 'ko', 'skriv_leder')
        svar = self._post(leder, sti, {'navn': 'TG Samvirke'})
        self.assertIn(svar.status_code, (200, 201), svar.content)
        self.assertTrue(EksternRessurs.objects.filter(navn='TG Samvirke').exists())


class MigrasjonenTests(_Grunnlag):
    """`0027` fyller pekeren for hendelsene som alt finnes, og listene."""

    def _fyll(self):
        from django.apps import apps
        importlib.import_module('ko.migrations.0027_hendelse_beskrivelse_og_varsling').fyll(apps, None)

    def test_pekeren_fylles_bare_med_beskrivelsen_fra_opprettelsen(self):
        med = self._hendelse(beskrivelse='Røyk')
        uten = self._hendelse()
        services.skriv_linje(self.vakt, 'kommentar fra en annen', bruker=self.per, hendelse=uten)
        sen = self._hendelse()
        sen_linje = services.skriv_linje(self.vakt, 'for sent', bruker=self.kari, hendelse=sen)
        Logglinje.objects.filter(pk=sen_linje.pk).update(registrert_at=sen.opprettet_at + timedelta(minutes=5))
        fra_linje = services.skriv_linje(self.vakt, 'linja hendelsen ble laget av', bruker=self.kari)
        laget_fra = services.opprett_hendelse(self.vakt, 'Fra linje', bruker=self.kari, fra_linje=fra_linje)
        Hendelse.objects.update(beskrivelse_linje=None)

        self._fyll()

        self.assertEqual(Hendelse.objects.get(pk=med.pk).beskrivelse_linje.tekst, 'Røyk')
        for h in (uten, sen, laget_fra):
            with self.subTest(h=h.tittel):
                self.assertIsNone(Hendelse.objects.get(pk=h.pk).beskrivelse_linje_id)

    def test_standardlista_i_hver_portal_og_ingen_dubletter(self):
        from core.models import Vaktportal
        Vaktportal.objects.create(navn='Brannkorpset', slug='brannkorpset')
        # Testbasen er laget av migrasjonene, så standardportalen er alt seedet.
        EksternRessurs.objects.all().delete()
        self._fyll()
        self._fyll()
        for portal in Vaktportal.objects.all():
            with self.subTest(portal=portal.slug):
                navn = set(EksternRessurs.objects.filter(portal=portal).values_list('navn', flat=True))
                self.assertTrue({'Brann', 'Politi', 'AMK', 'LSKO'} <= navn)
                self.assertEqual(EksternRessurs.objects.filter(portal=portal, navn='AMK').count(), 1)


# ── Byggerne og avkryssingen i nettleseren ───────────────────────────────────

from patients.js_test_utils import (  # noqa: E402
    KO_JS, OPPDRAG_ENHET_JS, OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available,
    run_node,
)


class HodetINettleserenTests(TestCase):
    """`koBeskrivelseHtml`, `koEksterneHtml` og `koVarsle` kjørt i node.

    **Avkryssingen er regelen her:** delegeringen sender `el.value`, ikke
    `checked` (`hendelseArgumenter`), så boksen bærer tilstanden et trykk gir.
    Testen bygger boksen med den ekte byggeren og sender verdien den har gjennom
    `hendelseArgumenter`, som nettleseren gjør.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'hendelseArgumenter', '_handlerArgument')),
        (KO_JS, ('koKlokke', 'koBeskrivelse', 'koBeskrivelseHtml', 'koEksterneValg', 'koEksterneHtml',
                 'koDeltMerke', 'koDeltEtikett', 'koVarsle')),
    )
    PRE = """
        globalThis.window = { KO_EKSTERNE: [{id: 1, navn: 'Brann'}, {id: 2, navn: 'Politi <AMK>'}] };
        let koLinjer = new Map(); let koHendelser = new Map(); let koApenHendelseId = 7;
        let koBeskrivelseRedigeres = null; let oppdragsliste = [];
        const sendt = [];
        async function _koHendelsehandling(sti, kropp) { sendt.push([sti, kropp]); return { res: { ok: true }, data: {} }; }
        async function koHentLogg() {}
        function koHentOppdragPaaNytt() {}
        function koTidspunktISO(v) { return v ? 'ISO:' + v : null; }
        globalThis.document = { getElementById: () => null };
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kjor(self, snippet):
        return run_node(self.harness, self.PRE + snippet)

    def test_beskrivelsen_er_gjeldende_versjon_og_escapes(self):
        ut = self._kjor("""
            koLinjer.set(5, {id: 9, rot: 5, tekst: '<b>Røyk</b>', forfatter: 'per', korrigerer: 5,
                             tidspunkt: '2026-10-19T12:00:00Z', delt_at: '2026-10-19T12:01:00Z'});
            const h = {id: 7, beskrivelse_rot: 5, status: 'apen'};
            const kan = koBeskrivelseHtml(h, true), les = koBeskrivelseHtml(h, false);
            assert(kan.includes('&lt;b&gt;Røyk&lt;/b&gt;') && !kan.includes('<b>Røyk'), 'escapet');
            assert(kan.includes('oppdatert') && kan.includes('Delt'), 'retting og deling synes');
            assert(kan.includes('koBeskrivelseRediger') && !les.includes('koBeskrivelseRediger'),
                   'knappen bare for den som kan skrive');
            koLinjer.set(5, {id: 9, rot: 5, tekst: 'x', fjernet: true});
            assert(koBeskrivelse(h) === null, 'en fjernet beskrivelse står ikke i hodet');
            assert(koBeskrivelseHtml(h, false) === '', 'ingenting for den som leser');
            assert(koBeskrivelseHtml(h, true).includes('Legg til beskrivelse'));
            assert(koBeskrivelse({id: 1, beskrivelse_rot: null}) === null);
        """)

    def test_boksen_baerer_tilstanden_et_trykk_gir_og_varsler_riktig(self):
        ut = self._kjor("""
            const h = {id: 7, status: 'apen', varslinger: [
              {ressurs_id: 2, navn: 'Politi <AMK>', tid: '2026-10-19T12:00:00Z', av: 'kari'},
              {ressurs_id: 3, navn: 'Tatt ut av lista', tid: '2026-10-19T12:00:00Z', av: 'kari'}]};
            const html = koEksterneHtml(h, true);
            assert(!html.includes('Politi <AMK>') && html.includes('Politi &lt;AMK&gt;'), 'navnet escapes');
            assert(html.includes('Tatt ut av lista'), 'en varsling uten plass i lista vises likevel');
            // Plukk boksene ut av markupen og send dem gjennom delegeringen.
            const bokser = [...html.matchAll(/<input type="checkbox"[^>]*>/g)].map((m) => {
              const a = (n) => (m[0].match(new RegExp(n + '="([^"]*)"')) || [])[1];
              return { dataset: { id: a('data-id'), felt: a('data-felt') }, value: a('value'),
                       checked: / checked/.test(m[0]), disabled: / disabled/.test(m[0]) };
            });
            (async () => {
              for (const b of bokser.slice(0, 2)) await koVarsle(...hendelseArgumenter(b));
              console.log(JSON.stringify({sendt, bokser: bokser.map((b) => [b.value, b.checked, b.disabled])}));
            })();
        """)
        r = json.loads([l for l in ut.strip().splitlines() if l.startswith('{')][-1])
        self.assertEqual(r['bokser'], [['1', False, False], ['0', True, False], ['0', True, False]])
        self.assertEqual(r['sendt'], [
            ['/ko/api/hendelser/7/varsling/', {'ressurs_id': 1, 'varslet': True}],
            ['/ko/api/hendelser/7/varsling/', {'ressurs_id': 2, 'varslet': False}],
        ])

    def test_lukket_eller_les_gir_laaste_bokser_og_intet_tidsfelt(self):
        self._kjor("""
            const h = {id: 7, status: 'lukket', varslinger: []};
            for (const html of [koEksterneHtml(h, true), koEksterneHtml({...h, status: 'apen'}, false)]) {
              const bokser = html.match(/<input type="checkbox"[^>]*>/g);
              assert(bokser.length === 2 && bokser.every((b) => b.includes(' disabled')), html);
              assert(!html.includes('ko-varsling-tid'), 'ingen tid å sette');
            }
            window.KO_EKSTERNE = [];
            assert(koEksterneHtml({id: 7, status: 'apen', varslinger: []}, true) === '', 'tom liste, ingen rad');
        """)

    def test_tid_sendes_bare_med_en_avkryssing(self):
        ut = self._kjor("""
            globalThis.document = { getElementById: (id) => (id === 'ko-varsling-tid' ? { value: '14:20' } : null) };
            (async () => {
              await koVarsle(1, 'varslet', '1');
              await koVarsle(1, 'varslet', '0');
              console.log(JSON.stringify(sendt.map((s) => s[1])));
            })();
        """)
        linjer = [l for l in ut.strip().splitlines() if l.startswith('[')]
        self.assertEqual(json.loads(linjer[-1]), [
            {'ressurs_id': 1, 'varslet': True, 'tidspunkt': 'ISO:14:20'},
            {'ressurs_id': 1, 'varslet': False},
        ])


class TalegruppeINettleserenTests(TestCase):
    """Hodets TG-rad: valgene, knappene og escapingen."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(((PORTAL_UTILS_JS, ('escapeHtml',)),
                                      (KO_JS, ('koTalegruppeValg', 'koTalegruppeHtml', 'koSettTalegruppe'))))

    def test_knappene_bare_for_den_som_kan_paa_en_aapen_hendelse(self):
        run_node(self.harness, """
            globalThis.window = { KO_TALEGRUPPER: ['SAMVIRKE 2', 'TG <x>'] };
            const h = {id: 4, status: 'apen', talegruppe: 'GAMMEL', talegruppe_delt: true};
            const kan = koTalegruppeHtml(h, true);
            assert(kan.includes('data-id="4:intern"') && kan.includes('data-id="4:del"'), kan);
            assert(kan.includes('TG &lt;x&gt;') && !kan.includes('TG <x>'), 'escapet');
            assert(kan.includes('<option value="GAMMEL" selected>'), 'den den står på, også utenfor lista');
            assert(kan.includes('Delt med bilene'));
            for (const html of [koTalegruppeHtml(h, false), koTalegruppeHtml({...h, status: 'lukket'}, true)]) {
              assert(!html.includes('koSettTalegruppe') && html.includes('GAMMEL'), html);
            }
            assert(koTalegruppeHtml({id: 4, status: 'apen', talegruppe: ''}, false) === '', 'ingenting å vise');
            window.KO_TALEGRUPPER = [];
            assert(koTalegruppeHtml({id: 4, status: 'apen', talegruppe: ''}, true) === '', 'tom liste');
        """)

    def test_knappen_sender_valget_og_delingen(self):
        ut = run_node(self.harness, """
            const sendt = [];
            async function _koHendelsehandling(sti, kropp) { sendt.push([sti, kropp]); return { res: { ok: true }, data: {} }; }
            async function koHentLogg() {}
            function koHentOppdragPaaNytt() {}
            globalThis.document = { getElementById: (id) => (id === 'ko-tg-valg' ? { value: 'SAMVIRKE 2' } : null) };
            (async () => {
              await koSettTalegruppe('4:del');
              await koSettTalegruppe('4:intern');
              console.log(JSON.stringify(sendt));
            })();
        """)
        linje = [l for l in ut.splitlines() if l.startswith('[')][-1]
        self.assertEqual(json.loads(linje), [
            ['/ko/api/hendelser/4/talegruppe/', {'talegruppe': 'SAMVIRKE 2', 'del': True}],
            ['/ko/api/hendelser/4/talegruppe/', {'talegruppe': 'SAMVIRKE 2', 'del': False}],
        ])


class OppdragetINettleserenTests(TestCase):
    """«Meldt av» og «Varslet» i bilen og hos sentralbordet, escapet."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def test_begge_byggerne_viser_og_escaper(self):
        for fil, navn in ((OPPDRAG_ENHET_JS, 'hendelseinfoBlokk'), (OPPDRAG_SENTRAL_JS, '_hendelseinfoHtml')):
            with self.subTest(navn=navn):
                harness = build_harness(((PORTAL_UTILS_JS, ('escapeHtml', 'klokke')), (fil, (navn,))))
                run_node(harness, f"""
                    const o = {{hendelse_id: 5, hendelse_melder: 'AMK, Andre (<script>)', hendelse_talegruppe: 'SAMV <2>',
                               hendelse_varslet: [{{navn: 'Brann <x>', tid: '2026-10-19T12:00:00Z'}}]}};
                    const html = {navn}(o);
                    assert(html.includes('TG: <b>SAMV &lt;2&gt;</b>'), html);
                    assert({navn}({{hendelse_id: 5, hendelse_talegruppe: 'S1'}}).includes('S1'), 'TG alene');
                    assert(html.includes('Meldt av: <b>AMK, Andre (&lt;script&gt;)</b>'), html);
                    assert(html.includes('Brann &lt;x&gt;') && !html.includes('<script>'), html);
                    assert({navn}({{hendelse_id: null, hendelse_melder: 'AMK'}}) === '', 'uten hendelse');
                    assert({navn}({{hendelse_id: 5, hendelse_melder: '', hendelse_varslet: []}}) === '', 'tomt');
                    assert({navn}({{hendelse_id: 5, hendelse_melder: 'AMK'}}).includes('AMK'), 'uten varslinger');
                """)


class KallstedeneTests(TestCase):
    """Gjennom de ekte inngangene: hendelsen åpnet i vinduet, og bilens kort.
    Byggertestene over lar kallstedet forsvinne uten at noe blir rødt
    (`CLAUDE.md`, «Testen kaller hjelperen selv»)."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def test_hodet_viser_beskrivelsen_og_avkryssingen_over_lagene(self):
        from ko.tests_js import HendelsenIHendelsesvinduetTests as Vindu
        h5 = dict(Vindu.H5, beskrivelse_rot=2,
                  varslinger=[{'ressurs_id': 1, 'navn': 'Brann', 'tid': '2026-10-19T12:00:00Z', 'av': 'kari'}])
        t = Vindu()
        t.H5 = h5
        ut = t._kjor("""
            window.KO_EKSTERNE = [{id: 1, navn: 'Brann'}, {id: 2, navn: 'Politi'}];
            window.KO_TALEGRUPPER = ['SAMVIRKE 2'];
            koLinjer.set(2, {id: 2, rot: 2, kilde: 'operator', hendelse_id: 5, systemkode: '',
                             tekst: 'Røyk fra telt B', forfatter: 'kari', tidspunkt: '2026-10-19T12:00:00Z'});
            koApneHendelse('5');
            const d = el('ko-hendelse-detalj').innerHTML;
            const besk = d.indexOf('Røyk fra telt B'), varsle = d.indexOf('data-action="koVarsle"'),
                  lag = d.indexOf('Lag:'), sted = d.indexOf('bi-geo-alt'), tg = d.indexOf('koSettTalegruppe');
            console.log(JSON.stringify([sted < tg && tg < besk, besk < varsle, varsle < lag,
                                        d.includes('h-beskrivelse-merke'), (d.match(/koVarsle/g) || []).length]));
        """)
        self.assertEqual(json.loads(ut[-1]), [True, True, True, True, 2],
                     'sted, TG, beskrivelse, varslet, lag — og linja i tråden merket')

    def test_bilens_kort_viser_melder_og_varslede(self):
        from oppdrag.tests_xss import EnhetEscapingOppforselTests as E
        harness = build_harness(E.HARNESS)
        o = {'id': 1, 'status': 'rykker_ut', 'status_navn': 'Rykker ut', 'hastegrad': 'Akutt', 'nummer': 3,
             'problemstilling': 'Fall', 'lokasjon_navn': 'Scene', 'enheter': [], 'hendelse_id': 5,
             'hendelse_nummer': 5, 'hendelse_melder': 'AMK',
             'hendelse_varslet': [{'navn': 'Brann', 'tid': '2026-10-19T12:00:00Z'}]}
        for fn in ('renderAktivt', 'renderVentende'):
            with self.subTest(fn=fn):
                ut = run_node(harness, E.STUBB + f"""
                    globalThis.mineOppdrag = [{json.dumps(dict(o, status='venter' if fn == 'renderVentende' else 'rykker_ut'))}];
                    const el = {{ innerHTML: '' }};
                    globalThis.document = {{ getElementById: () => el }};
                    {fn}();
                    console.log(el.innerHTML.includes('Meldt av: <b>AMK</b>'), el.innerHTML.includes('Brann'));
                """)
                self.assertIn('true true', ut)
