"""Hendelsene (pulje 5) — reglene, portene og hva som står i loggen.

Tyngden ligger i tjenestelaget, som `CLAUDE.md` sier: hver gren i
`ko/services.py` sin hendelsesdel prøves, fordi en feil der legger seg i data.
Portene på viewene prøves som porter. Markupen prøves ikke her; grupperingen
på tavla er en JS-regel og prøves i `ko/tests_js.py`.

**Prøvene går gjennom den ekte inngangen der det finnes én.** Å knytte et
oppdrag prøves gjennom `knytt_oppdrag`, og loggen leses tilbake etterpå — ikke
gjennom `systemlinje()` direkte. Muter kallstedet, ikke bare funksjonen.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.models import AppSetting
from core.vakt import hent_aktiv_vakt, vakt_for_year
from ko import services, systemlinjer
from ko.models import (HENDELSE_APEN, HENDELSE_LUKKET, KILDE_SYSTEM, Hendelse,
                       Logglinje)
from oppdrag import choices
from oppdrag import services as oservices
from oppdrag.models import Enhet, Lokasjon, Oppdrag


def _bruker(navn, **kwargs):
    return CustomUser.objects.create_user(
        username=navn, password='x', must_change_password=False, **kwargs)


def _gi(bruker, modul, nivaa):
    ModulTilgang.objects.update_or_create(
        bruker=bruker, modul_slug=modul, defaults={'nivaa': nivaa})
    return bruker


class _Grunnlag(TestCase):

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.operator = _bruker('ko1')
        self.enhet = Enhet.objects.create(navn='HGSD 56')
        self.lokasjon = Lokasjon.objects.create(navn='Scene sør')

    def _oppdrag(self, **felt):
        felt.setdefault('problemstilling', 'Fall')
        felt.setdefault('hastegrad', choices.HASTEGRAD[0])
        return Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=oservices.neste_oppdragsnummer(self.vakt),
            enhet=self.enhet, lokasjon=self.lokasjon, **felt)

    def _hendelse(self, tittel='Slagsmål ved scene sør', **kw):
        return services.opprett_hendelse(self.vakt, tittel, bruker=self.operator, **kw)

    def _systemkoder(self):
        return list(Logglinje.objects.filter(kilde=KILDE_SYSTEM)
                    .order_by('id').values_list('systemkode', flat=True))

    def _siste_systemlinje(self):
        return Logglinje.objects.filter(kilde=KILDE_SYSTEM).order_by('-id').first()


class NummereringTests(_Grunnlag):
    """§6: to uavhengige serier, begge per vakt, begge fra 1."""

    def test_starter_paa_1_og_teller_opp(self):
        a = self._hendelse('A')
        b = self._hendelse('B')
        self.assertEqual((a.hendelsesnummer, b.hendelsesnummer), (1, 2))

    def test_serien_er_uavhengig_av_oppdragsserien(self):
        self._oppdrag()
        self._oppdrag()
        h = self._hendelse()
        self.assertEqual(h.hendelsesnummer, 1, 'H-serien skal ikke arve O-serien')

    def test_telleren_gjenskapes_fra_dataene(self):
        """En slettet `AppSetting`-rad skal ikke gi nummer 1 om igjen — da
        kolliderer den med `unikt_hendelsesnummer_per_vakt`."""
        self._hendelse('A')
        self._hendelse('B')
        AppSetting.objects.filter(key__startswith='next_hendelse_nr_vakt_').delete()
        self.assertEqual(self._hendelse('C').hendelsesnummer, 3)

    def test_telleren_er_unntatt_audit(self):
        """Telleren er noe maskinen har talt (`core/signals.py`)."""
        from core.signals import nokkel_logges
        self.assertFalse(nokkel_logges(f'next_hendelse_nr_vakt_{self.vakt.pk}'))

    def test_formene(self):
        self.assertEqual(services.hendelsesnr(12), 'H12')
        self.assertEqual(oservices.oppdragsnr(45), 'O45')


class OpprettelsenTests(_Grunnlag):

    def test_fryser_operatoren_og_skriver_linje(self):
        h = self._hendelse()
        self.assertEqual(h.opprettet_av_navn, 'ko1')
        self.assertEqual(h.status, HENDELSE_APEN)
        linje = self._siste_systemlinje()
        self.assertEqual(linje.systemkode, systemlinjer.HENDELSE_OPPRETTET)
        self.assertEqual(linje.forfatter_navn, 'ko1', 'handlingen skal bære hvem')
        self.assertEqual(linje.hendelse_id, h.pk, 'linja hører til hendelsen')
        self.assertIn('H1 opprettet · Slagsmål ved scene sør',
                      systemlinjer.tegn(linje.systemkode, linje.systemdata))

    def test_fra_linje_lar_linja_staa_og_peker_tilbake(self):
        """§4.5: flyttes linja inn i hendelsen, får loggen et hull."""
        linje = services.skriv_linje(self.vakt, 'To slåss ved scene sør', bruker=self.operator)
        h = self._hendelse(fra_linje=linje)
        linje.refresh_from_db()
        self.assertEqual(h.opprettet_fra_linje_id, linje.pk)
        self.assertEqual(linje.hendelse_id, h.pk)
        self.assertEqual(linje.tekst, 'To slåss ved scene sør', 'linja er urørt')
        self.assertTrue(Logglinje.objects.filter(pk=linje.pk, korrigert_av__isnull=True).exists())

    def test_linje_som_alt_hoerer_til_beholder_sin(self):
        linje = services.skriv_linje(self.vakt, 'x', bruker=self.operator)
        a = self._hendelse('A', fra_linje=linje)
        self._hendelse('B', fra_linje=linje)
        linje.refresh_from_db()
        self.assertEqual(linje.hendelse_id, a.pk)

    def test_linje_fra_annen_vakt_avvises(self):
        annen = vakt_for_year(2001)
        linje = services.skriv_linje(annen, 'x', bruker=self.operator)
        with self.assertRaises(services.Ugyldig):
            self._hendelse(fra_linje=linje)

    def test_tittel_kreves_og_har_tak(self):
        with self.assertRaises(services.Ugyldig):
            self._hendelse('   ')
        with self.assertRaises(services.Ugyldig):
            self._hendelse('x' * (services.MAKS_TITTEL + 1))
        self.assertEqual(len(self._hendelse('x' * services.MAKS_TITTEL).tittel),
                         services.MAKS_TITTEL)

    def test_lokasjonen_fryses_som_navn(self):
        h = self._hendelse(lokasjon=self.lokasjon)
        self.lokasjon.navn = 'Scene nord'
        self.lokasjon.save()
        h.refresh_from_db()
        self.assertEqual(h.lokasjon_navn, 'Scene sør')


class RedigeringTests(_Grunnlag):
    """§7.1: hodet er det ene delte redigerbare — versjon og 409."""

    def test_riktig_versjon_gaar_gjennom_og_teller_opp(self):
        h = self._hendelse()
        services.rediger_hendelse(h, bruker=self.operator, versjon=1, tittel='Ny tittel')
        h.refresh_from_db()
        self.assertEqual((h.tittel, h.versjon), ('Ny tittel', 2))

    def test_feil_versjon_er_konflikt(self):
        h = self._hendelse()
        services.rediger_hendelse(h, bruker=self.operator, versjon=1, tittel='Ny')
        with self.assertRaises(services.Konflikt):
            services.rediger_hendelse(h, bruker=self.operator, versjon=1, tittel='Nyere')

    def test_uten_versjon_er_konflikt(self):
        """En klient som ikke sier hva den så, kan ikke vite at den skriver
        over noe."""
        h = self._hendelse()
        with self.assertRaises(services.Konflikt):
            services.rediger_hendelse(h, bruker=self.operator, versjon=None, tittel='Ny')

    def test_ingenting_endret_avvises(self):
        h = self._hendelse('Samme')
        with self.assertRaises(services.Ugyldig):
            services.rediger_hendelse(h, bruker=self.operator, versjon=1, tittel='Samme')

    def test_lokasjonen_kan_settes_og_toemmes(self):
        h = self._hendelse()
        services.rediger_hendelse(h, bruker=self.operator, versjon=1,
                                  lokasjon=self.lokasjon, sett_lokasjon=True)
        h.refresh_from_db()
        self.assertEqual((h.lokasjon_id, h.lokasjon_navn), (self.lokasjon.pk, 'Scene sør'))
        services.rediger_hendelse(h, bruker=self.operator, versjon=2,
                                  lokasjon=None, sett_lokasjon=True)
        h.refresh_from_db()
        self.assertEqual((h.lokasjon_id, h.lokasjon_navn), (None, ''))

    def test_redigering_gir_ingen_systemlinje(self):
        """Regel 2 i `ko/systemlinjer.py`: feltendringer fører `audit/`."""
        h = self._hendelse()
        foer = len(self._systemkoder())
        services.rediger_hendelse(h, bruker=self.operator, versjon=1, tittel='Ny')
        self.assertEqual(len(self._systemkoder()), foer)


class LukkingTests(_Grunnlag):
    """§4.6: 409 med antallet, gjennom med `confirm`, og det står på linja."""

    def test_uten_oppdrag_lukkes_rett_fram(self):
        h = self._hendelse()
        services.lukk_hendelse(h, bruker=self.operator)
        h.refresh_from_db()
        self.assertEqual(h.status, HENDELSE_LUKKET)
        self.assertEqual(h.lukket_av_navn, 'ko1')
        self.assertIsNotNone(h.lukket_at)
        linje = self._siste_systemlinje()
        self.assertEqual(linje.systemkode, systemlinjer.HENDELSE_LUKKET)
        self.assertEqual(systemlinjer.tegn(linje.systemkode, linje.systemdata),
                         'H1 lukket · Slagsmål ved scene sør')

    def test_aapne_oppdrag_sperrer_med_antallet(self):
        h = self._hendelse()
        o1 = self._oppdrag()
        o2 = self._oppdrag()
        services.knytt_oppdrag(o1, h, bruker=self.operator)
        services.knytt_oppdrag(o2, h, bruker=self.operator)
        with self.assertRaises(services.HarApneOppdrag) as cm:
            services.lukk_hendelse(h, bruker=self.operator)
        self.assertEqual(cm.exception.antall, 2)
        h.refresh_from_db()
        self.assertEqual(h.status, HENDELSE_APEN, 'ingenting skal ha skjedd')

    def test_ferdige_oppdrag_teller_ikke(self):
        h = self._hendelse()
        o = self._oppdrag(status=choices.TERMINAL)
        services.knytt_oppdrag(o, h, bruker=self.operator)
        services.lukk_hendelse(h, bruker=self.operator)
        h.refresh_from_db()
        self.assertEqual(h.status, HENDELSE_LUKKET)

    def test_confirm_gaar_gjennom_og_det_staar_paa_linja(self):
        h = self._hendelse()
        services.knytt_oppdrag(self._oppdrag(), h, bruker=self.operator)
        services.lukk_hendelse(h, bruker=self.operator, confirm=True)
        linje = self._siste_systemlinje()
        self.assertEqual(linje.systemdata['apne_oppdrag'], 1)
        self.assertIn('— med 1 åpent oppdrag',
                      systemlinjer.tegn(linje.systemkode, linje.systemdata))

    def test_lukket_kan_ikke_lukkes_igjen(self):
        h = self._hendelse()
        services.lukk_hendelse(h, bruker=self.operator)
        with self.assertRaises(services.Ugyldig):
            services.lukk_hendelse(h, bruker=self.operator)


class GjenaapningTests(_Grunnlag):
    """André, 18. sep. 2026: lukkingen var en misforståelse eller et feilklikk
    — og at den ble åpnet igjen **skal logges**."""

    def test_aapnes_igjen_og_logges(self):
        h = self._hendelse()
        services.lukk_hendelse(h, bruker=self.operator)
        services.gjenapne_hendelse(h, bruker=self.operator)
        h.refresh_from_db()
        self.assertEqual(h.status, HENDELSE_APEN)
        self.assertIsNone(h.lukket_at)
        self.assertEqual(h.lukket_av_navn, '')
        linje = self._siste_systemlinje()
        self.assertEqual(linje.systemkode, systemlinjer.HENDELSE_GJENAPNET)
        self.assertEqual(linje.forfatter_navn, 'ko1')
        self.assertIn('åpnet igjen', systemlinjer.tegn(linje.systemkode, linje.systemdata))
        self.assertEqual(self._systemkoder()[-3:], [
            systemlinjer.HENDELSE_OPPRETTET, systemlinjer.HENDELSE_LUKKET,
            systemlinjer.HENDELSE_GJENAPNET], 'historien står i loggen, i rekkefølge')

    def test_aapen_kan_ikke_aapnes(self):
        with self.assertRaises(services.Ugyldig):
            services.gjenapne_hendelse(self._hendelse(), bruker=self.operator)


class KnytningTests(_Grunnlag):
    """`Oppdrag.hendelse` skrives bare her. Nummeret rører ingen."""

    def test_knytt_skriver_pekeren_og_linja(self):
        h = self._hendelse()
        o = self._oppdrag()
        nr = o.oppdragsnummer
        services.knytt_oppdrag(o, h, bruker=self.operator)
        o.refresh_from_db()
        self.assertEqual(o.hendelse_id, h.pk)
        self.assertEqual(o.oppdragsnummer, nr, 'nummeret identifiserer, FK-en relaterer')
        linje = self._siste_systemlinje()
        self.assertEqual(linje.systemkode, systemlinjer.OPPDRAG_KNYTTET)
        self.assertEqual(systemlinjer.tegn(linje.systemkode, linje.systemdata),
                         f'O{nr} knyttet til H1')
        self.assertEqual(linje.hendelse_id, h.pk)

    def test_flytt_og_loesne_tegnes_ulikt(self):
        a = self._hendelse('A')
        b = self._hendelse('B')
        o = self._oppdrag()
        services.knytt_oppdrag(o, a, bruker=self.operator)
        services.knytt_oppdrag(o, b, bruker=self.operator)
        flytt = self._siste_systemlinje()
        self.assertEqual(systemlinjer.tegn(flytt.systemkode, flytt.systemdata),
                         f'O{o.oppdragsnummer} flyttet fra H1 til H2')
        services.knytt_oppdrag(o, None, bruker=self.operator)
        losne = self._siste_systemlinje()
        self.assertEqual(systemlinjer.tegn(losne.systemkode, losne.systemdata),
                         f'O{o.oppdragsnummer} løsnet fra H2')
        self.assertEqual(losne.hendelse_id, b.pk, 'løsningen hører til hendelsen den forlot')
        o.refresh_from_db()
        self.assertIsNone(o.hendelse_id)

    def test_lukket_hendelse_tar_ikke_imot(self):
        h = self._hendelse()
        services.lukk_hendelse(h, bruker=self.operator)
        with self.assertRaises(services.Ugyldig):
            services.knytt_oppdrag(self._oppdrag(), h, bruker=self.operator)

    def test_annen_vakt_avvises(self):
        annen = vakt_for_year(2001)
        h = services.opprett_hendelse(annen, 'Der', bruker=self.operator)
        with self.assertRaises(services.Ugyldig):
            services.knytt_oppdrag(self._oppdrag(), h, bruker=self.operator)

    def test_ingenting_endret_avvises(self):
        with self.assertRaises(services.Ugyldig):
            services.knytt_oppdrag(self._oppdrag(), None, bruker=self.operator)

    def test_hendelser_for_teller_riktig(self):
        h = self._hendelse()
        services.knytt_oppdrag(self._oppdrag(), h, bruker=self.operator)
        services.knytt_oppdrag(self._oppdrag(status=choices.TERMINAL), h, bruker=self.operator)
        rad = services.hendelser_for(self.vakt)[0]
        self.assertEqual((rad.antall_oppdrag, rad.apne_oppdrag), (2, 1))


class OppryddingenTests(_Grunnlag):

    def test_gamle_hendelser_slettes_og_oppdraget_staar_igjen(self):
        h = self._hendelse()
        o = self._oppdrag()
        services.knytt_oppdrag(o, h, bruker=self.operator)
        Hendelse.objects.filter(pk=h.pk).update(
            opprettet_at=timezone.now() - timedelta(days=services.DAGER_STANDARD + 1))
        services.slett_utlopte()
        self.assertFalse(Hendelse.objects.filter(pk=h.pk).exists())
        o.refresh_from_db()
        self.assertIsNone(o.hendelse_id)
        self.assertTrue(Oppdrag.objects.filter(pk=o.pk).exists())

    def test_ferske_hendelser_staar(self):
        h = self._hendelse()
        services.slett_utlopte()
        self.assertTrue(Hendelse.objects.filter(pk=h.pk).exists())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(_Grunnlag):
    """Portene, ikke feltene. Nivåene i `ko/views.py` sin tabell."""

    def setUp(self):
        super().setUp()
        self.leser = _gi(_bruker('leser'), 'ko', 'les')
        _gi(self.operator, 'ko', 'skriv_full')
        _gi(self.operator, 'oppdrag', 'skriv_full')
        self.bare_ko = _gi(_bruker('bareko'), 'ko', 'skriv_full')

    def _klient(self, bruker):
        c = Client()
        c.force_login(bruker)
        return c

    def _post(self, bruker, sti, kropp=None):
        return self._klient(bruker).post(
            sti, data=json.dumps(kropp or {}), content_type='application/json')

    def test_les_kan_ikke_opprette(self):
        self.assertEqual(self._post(self.leser, '/ko/api/hendelser/ny/', {'tittel': 'x'}).status_code, 403)

    def test_skriv_full_oppretter(self):
        svar = self._post(self.operator, '/ko/api/hendelser/ny/',
                          {'tittel': 'Brann i telt', 'lokasjon_id': self.lokasjon.pk})
        self.assertEqual(svar.status_code, 201)
        data = svar.json()['data']
        self.assertEqual((data['kode'], data['lokasjon_navn'], data['status']),
                         ('H1', 'Scene sør', 'apen'))

    def test_ukjent_lokasjon_er_400_ikke_stille_none(self):
        svar = self._post(self.operator, '/ko/api/hendelser/ny/',
                          {'tittel': 'x', 'lokasjon_id': 9999})
        self.assertEqual(svar.status_code, 400)

    def test_fra_linje_utenfor_vakta_er_404(self):
        annen = vakt_for_year(2001)
        linje = services.skriv_linje(annen, 'x', bruker=self.operator)
        svar = self._post(self.operator, '/ko/api/hendelser/ny/',
                          {'tittel': 'x', 'fra_linje': linje.pk})
        self.assertEqual(svar.status_code, 404)

    def test_lukk_svarer_409_med_antallet(self):
        h = self._hendelse()
        services.knytt_oppdrag(self._oppdrag(), h, bruker=self.operator)
        svar = self._post(self.operator, f'/ko/api/hendelser/{h.pk}/lukk/')
        self.assertEqual(svar.status_code, 409)
        self.assertEqual(svar.json()['apne_oppdrag'], 1)
        svar = self._post(self.operator, f'/ko/api/hendelser/{h.pk}/lukk/', {'confirm': True})
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(svar.json()['data']['status'], 'lukket')

    def test_gjenapne(self):
        h = self._hendelse()
        services.lukk_hendelse(h, bruker=self.operator)
        svar = self._post(self.operator, f'/ko/api/hendelser/{h.pk}/gjenapne/')
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(svar.json()['data']['status'], 'apen')

    def test_rediger_krever_versjon(self):
        h = self._hendelse()
        svar = self._post(self.operator, f'/ko/api/hendelser/{h.pk}/rediger/', {'tittel': 'Ny'})
        self.assertEqual(svar.status_code, 409)
        svar = self._post(self.operator, f'/ko/api/hendelser/{h.pk}/rediger/',
                          {'tittel': 'Ny', 'versjon': 1})
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(svar.json()['data']['versjon'], 2)

    def test_knytt_krever_skriv_i_begge_modulene(self):
        h = self._hendelse()
        o = self._oppdrag()
        svar = self._post(self.bare_ko, f'/ko/api/oppdrag/{o.pk}/hendelse/', {'hendelse_id': h.pk})
        self.assertEqual(svar.status_code, 403, 'ko:skriv_full alene skriver ikke på et oppdrag')
        svar = self._post(self.operator, f'/ko/api/oppdrag/{o.pk}/hendelse/', {'hendelse_id': h.pk})
        self.assertEqual(svar.status_code, 200)
        o.refresh_from_db()
        self.assertEqual(o.hendelse_id, h.pk)
        svar = self._post(self.operator, f'/ko/api/oppdrag/{o.pk}/hendelse/', {'hendelse_id': None})
        self.assertEqual(svar.status_code, 200)
        o.refresh_from_db()
        self.assertIsNone(o.hendelse_id)

    def test_hendelse_utenfor_vakta_er_404(self):
        annen = vakt_for_year(2001)
        h = services.opprett_hendelse(annen, 'Der', bruker=self.operator)
        self.assertEqual(self._post(self.operator, f'/ko/api/hendelser/{h.pk}/lukk/').status_code, 404)

    def test_loggen_baerer_hendelsene(self):
        """Ingen egen poller: lista følger med `logg_view`, hele hver gang."""
        h = self._hendelse()
        services.knytt_oppdrag(self._oppdrag(), h, bruker=self.operator)
        data = self._klient(self.leser).get('/ko/api/logg/').json()
        self.assertEqual(len(data['hendelser']), 1)
        self.assertEqual(data['hendelser'][0]['apne_oppdrag'], 1)
        linjer = [l for l in data['data'] if l['systemkode'] == systemlinjer.HENDELSE_OPPRETTET]
        self.assertEqual(linjer[0]['forfatter'], 'ko1')
        self.assertEqual(linjer[0]['hendelse_nummer'], 1)
        # `?siden=` gir ingen nye linjer, men hendelsene er der like fullt.
        siste = max(l['id'] for l in data['data'])
        data = self._klient(self.leser).get(f'/ko/api/logg/?siden={siste}').json()
        self.assertEqual(data['data'], [])
        self.assertEqual(len(data['hendelser']), 1)

    def test_oppdragslista_baerer_hendelsen_og_etag_en_foelger(self):
        """Tavla grupperer på feltene i `/oppdrag/api/oppdrag/`, og å knytte
        rører verken status eller tidspunkt — uten ETag-leddet sto
        grupperingen gammel til neste stempling."""
        h = self._hendelse('Brann')
        o = self._oppdrag()
        c = self._klient(self.operator)
        svar = c.get('/oppdrag/api/oppdrag/')
        foer = svar['ETag']
        rad = svar.json()['data'][0]
        self.assertEqual((rad['hendelse_id'], rad['hendelse_nummer'], rad['hendelse_tittel']),
                         (None, None, ''))
        services.knytt_oppdrag(o, h, bruker=self.operator)
        svar = c.get('/oppdrag/api/oppdrag/', HTTP_IF_NONE_MATCH=foer)
        self.assertEqual(svar.status_code, 200, 'skal ikke drukne i en 304')
        rad = svar.json()['data'][0]
        self.assertEqual((rad['hendelse_id'], rad['hendelse_nummer'], rad['hendelse_tittel']),
                         (h.pk, 1, 'Brann'))


class BackupTests(TestCase):
    """Sirkelen som ikke får finnes: oppdrag peker på ko, ko peker på oppdrag."""

    def test_ko_er_fri_for_oppdrag_og_oppdrag_krever_ko(self):
        from core.backup import registrer_alle_moduler
        from core.backup.rekkefolge import bindinger
        registrer_alle_moduler()
        kanter = bindinger()
        self.assertNotIn('oppdrag', kanter['ko'],
                         'Hendelse.lokasjon skal være strippet — ellers er det en sirkel')
        self.assertIn('ko', kanter['oppdrag'], 'Oppdrag.hendelse binder oppdrag til ko')
