"""Hendelsesloggen som egen flate (18. sep. 2026): prioritet, «bli med»,
festing og feltene i hodet — og fra 19. sep. 2026 lagene på hendelsen,
beskrivelsen som tillegg og melderen som avkryssing. Reglene og portene.

Tyngden ligger i tjenestelaget, som `CLAUDE.md` sier: hver gren i
`ko/services.py` prøves, fordi en feil der legger seg i data. Portene på
viewene prøves som porter. Markupen prøves i `ko/tests_js.py` og
`ko/tests.py`.

**Prøvene går gjennom den ekte inngangen.** «Den som skriver i hendelsen er
på den» prøves gjennom `skriv_linje`, `knytt_oppdrag`, `sett_prioritet` og
`rediger_hendelse` — ikke gjennom `bli_med` direkte. Muter kallstedet, ikke
bare funksjonen.
"""
from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from core.vakt import hent_aktiv_vakt, vakt_for_year
from ko import services, systemlinjer
from ko.models import (KILDE_SYSTEM, MELDER_VALG, PRIORITET_GRONN, PRIORITET_RANG,
                       PRIORITET_VALG, PRIORITET_VIKTIG, Hendelse,
                       HendelseDeltaker, HendelseLag, Logglinje)
from oppdrag import choices
from oppdrag import services as oservices
from oppdrag.models import Enhet, Lokasjon, Oppdrag
from vaktliste.models import Vaktliste
from vaktliste.test_helpers import LAG, gruppe, lag_ressurs


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
        self.andre = _bruker('ko2')
        self.enhet = Enhet.objects.create(navn='HGSD 56')
        self.lokasjon = Lokasjon.objects.create(navn='Scene sør')
        # Lagene er vaktlistas ressurser uten oppdragsenhet, i lista for
        # aktiv vakt — samme scope som kortene på tavla.
        self.vl = Vaktliste.objects.create(vakt=self.vakt)
        self.lag1 = lag_ressurs(vaktliste=self.vl, navn='Lag 1', gruppe=gruppe(LAG))
        self.lag2 = lag_ressurs(vaktliste=self.vl, navn='Lag 2', gruppe=gruppe(LAG))
        self.bil = lag_ressurs(vaktliste=self.vl, navn='Ambulanse 1', enhet=self.enhet)

    def _hendelse(self, tittel='Slagsmål', **kw):
        return services.opprett_hendelse(self.vakt, tittel, bruker=self.operator, **kw)

    def _oppdrag(self):
        return Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=oservices.neste_oppdragsnummer(self.vakt),
            enhet=self.enhet, lokasjon=self.lokasjon, problemstilling='Fall',
            hastegrad=choices.HASTEGRAD[0])

    def _deltakere(self, h):
        return sorted(h.deltakere.values_list('brukernavn', flat=True))

    def _siste_system(self):
        return Logglinje.objects.filter(kilde=KILDE_SYSTEM).order_by('-id').first()


class PrioritetTests(_Grunnlag):
    """Fem verdier, én rang, og endringen er en handling i loggen."""

    def test_standard_er_gronn(self):
        self.assertEqual(self._hendelse().prioritet, PRIORITET_GRONN)
        self.assertEqual(services.rens_prioritet(None), PRIORITET_GRONN)
        self.assertEqual(services.rens_prioritet('  '), PRIORITET_GRONN)

    def test_rangen_er_rekkefolgen_i_valgene(self):
        """Viktig først. `PRIORITET_RANG` utledes av `PRIORITET_VALG`, så de to
        kan ikke være uenige — men at rekkefølgen *er* denne, er en avgjørelse
        (André, 18. sep. 2026: Viktig, Rød, Gul, Grønn, Drift)."""
        self.assertEqual([v for v, _ in PRIORITET_VALG],
                         ['viktig', 'rod', 'gul', 'gronn', 'drift'])
        self.assertEqual(PRIORITET_RANG['viktig'], 0)
        self.assertLess(PRIORITET_RANG['rod'], PRIORITET_RANG['drift'])

    def test_ukjent_verdi_avvises_ikke_rettes(self):
        """«Kritisk» fra en gammel klient skal ikke stille bli Grønn."""
        with self.assertRaises(services.Ugyldig):
            services.rens_prioritet('kritisk')
        with self.assertRaises(services.Ugyldig):
            self._hendelse(prioritet='kritisk')
        self.assertEqual(Hendelse.objects.count(), 0, 'ingen rad, intet nummer brent')

    def test_prioritet_settes_ved_opprettelse_og_staar_paa_linja(self):
        h = self._hendelse(prioritet='Viktig')
        self.assertEqual(h.prioritet, PRIORITET_VIKTIG)
        self.assertIn('Viktig', systemlinjer.tegn(self._siste_system().systemkode,
                                                  self._siste_system().systemdata))

    def test_gronn_staar_ikke_paa_opprettelseslinja(self):
        """Normaltilstanden er ikke et merke — et merke på hver hendelse er støy."""
        self._hendelse(prioritet='gronn')
        tekst = systemlinjer.tegn(self._siste_system().systemkode, self._siste_system().systemdata)
        self.assertNotIn('Grønn', tekst)

    def test_endring_logges_med_fra_og_til_og_hvem(self):
        h = self._hendelse()
        services.sett_prioritet(h, 'rod', bruker=self.andre)
        h.refresh_from_db()
        self.assertEqual(h.prioritet, 'rod')
        linje = self._siste_system()
        self.assertEqual(linje.systemkode, systemlinjer.HENDELSE_PRIORITET)
        self.assertEqual(linje.forfatter_navn, 'ko2')
        self.assertEqual(linje.hendelse_id, h.pk)
        tekst = systemlinjer.tegn(linje.systemkode, linje.systemdata)
        self.assertIn('satt til Rød', tekst)
        self.assertIn('var Grønn', tekst)

    def test_samme_prioritet_er_ingen_endring(self):
        h = self._hendelse(prioritet='gul')
        foer = Logglinje.objects.count()
        with self.assertRaises(services.Ugyldig):
            services.sett_prioritet(h, 'gul', bruker=self.operator)
        self.assertEqual(Logglinje.objects.count(), foer, 'ingen linje for ingenting')

    def test_endringen_teller_versjonen_opp(self):
        """Den som redigerer hodet samtidig skal få vite at noe skjedde."""
        h = self._hendelse()
        v = h.versjon
        services.sett_prioritet(h, 'drift', bruker=self.operator)
        self.assertEqual(h.versjon, v + 1)


class BliMedTests(_Grunnlag):
    """«Hvis en bruker registrerer noe i hendelsen så er de automatisk med»
    (André, 18. sep. 2026). Vises, styrer ingenting."""

    def test_den_som_oppretter_er_med(self):
        h = self._hendelse()
        self.assertEqual(self._deltakere(h), ['ko1'])

    def test_kommentar_melder_inn(self):
        h = self._hendelse()
        services.skriv_linje(self.vakt, 'Lag 1 på stedet', bruker=self.andre, hendelse=h)
        self.assertEqual(self._deltakere(h), ['ko1', 'ko2'])

    def test_linje_uten_hendelse_melder_ingen_inn(self):
        h = self._hendelse()
        services.skriv_linje(self.vakt, 'kaffe', bruker=self.andre)
        self.assertEqual(self._deltakere(h), ['ko1'])

    def test_oppdrag_knyttet_melder_inn(self):
        h = self._hendelse()
        services.knytt_oppdrag(self._oppdrag(), h, bruker=self.andre)
        self.assertEqual(self._deltakere(h), ['ko1', 'ko2'])

    def test_loesning_melder_ingen_inn(self):
        h = self._hendelse()
        o = self._oppdrag()
        services.knytt_oppdrag(o, h, bruker=self.operator)
        tredje = _bruker('ko3')
        services.knytt_oppdrag(o, None, bruker=tredje)
        self.assertNotIn('ko3', self._deltakere(h))

    def test_prioritet_og_redigering_melder_inn(self):
        h = self._hendelse()
        services.sett_prioritet(h, 'rod', bruker=self.andre)
        self.assertIn('ko2', self._deltakere(h))
        tredje = _bruker('ko3')
        services.rediger_hendelse(h, bruker=tredje, versjon=h.versjon, melder_typer=['amk'])
        self.assertIn('ko3', self._deltakere(h))

    def test_idempotent_og_navnet_fryses(self):
        h = self._hendelse()
        self.assertFalse(services.bli_med(h, self.operator), 'alt med')
        self.assertTrue(services.bli_med(h, self.andre))
        self.assertFalse(services.bli_med(h, self.andre))
        self.assertEqual(HendelseDeltaker.objects.filter(hendelse=h).count(), 2)
        self.andre.delete()
        self.assertEqual(self._deltakere(h), ['ko1', 'ko2'], 'navnet står etter at kontoen er borte')

    def test_anonym_og_ingen_melder_ingen_inn(self):
        from django.contrib.auth.models import AnonymousUser
        h = self._hendelse()
        self.assertFalse(services.bli_med(h, None))
        self.assertFalse(services.bli_med(h, AnonymousUser()))
        self.assertEqual(self._deltakere(h), ['ko1'])


class HodetTests(_Grunnlag):
    """Melder og beskrivelse: valideres før nummeret trekkes, redigeres med
    versjon."""

    def test_feltene_lagres_ved_opprettelse(self):
        h = self._hendelse(beskrivelse=' Mann ca. 40 ', melder_typer=['egen', 'andre'],
                           melder='arrangørvakt', lokasjon=self.lokasjon)
        self.assertEqual([t['tekst'] for t in h.beskrivelse_tillegg()], ['Mann ca. 40'])
        self.assertEqual(h.melder_typer, ['egen', 'andre'])
        self.assertEqual(h.melder, 'arrangørvakt')
        self.assertEqual(services.melder_tekst(h), 'Egen ressurs, Andre (arrangørvakt)')
        self.assertEqual(h.lokasjon_navn, 'Scene sør')

    def test_for_lange_felt_avvises_foer_nummeret_trekkes(self):
        """Telleren lar seg ikke rulle tilbake av en 400 — en avvist
        innsending som alt hadde hentet H14 ville etterlatt et hull."""
        for felt, verdi in (('beskrivelse', 'x' * (services.MAKS_BESKRIVELSE + 1)),
                            ('melder', 'x' * (services.MAKS_MELDER + 1))):
            with self.subTest(felt=felt):
                with self.assertRaises(services.Ugyldig):
                    self._hendelse(melder_typer=['andre'], **{felt: verdi})
        self.assertEqual(Hendelse.objects.count(), 0)
        h = self._hendelse()
        self.assertEqual(h.hendelsesnummer, 1, 'ingen nummer brent')

    def test_grensene_selv_er_lov(self):
        h = self._hendelse(beskrivelse='x' * services.MAKS_BESKRIVELSE,
                           melder_typer=['andre'], melder='x' * services.MAKS_MELDER)
        self.assertEqual(len(h.beskrivelse_tillegg()[0]['tekst']), services.MAKS_BESKRIVELSE)

    def test_rediger_melder(self):
        h = self._hendelse(melder_typer=['amk'])
        services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon,
                                  melder_typer=['politi', 'andre'], melder='publikum')
        h.refresh_from_db()
        self.assertEqual((h.melder_typer, h.melder), (['politi', 'andre'], 'publikum'))
        self.assertEqual(h.versjon, 2)

    def test_uendret_melder_er_ingen_endring(self):
        h = self._hendelse(melder_typer=['amk'])
        with self.assertRaises(services.Ugyldig):
            services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon,
                                      melder_typer=['amk'])
        h.refresh_from_db()
        self.assertEqual(h.versjon, 1)

    def test_versjonen_kreves_fortsatt(self):
        h = self._hendelse()
        with self.assertRaises(services.Konflikt):
            services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon + 1,
                                      melder_typer=['amk'])


class MelderTests(_Grunnlag):
    """Avkryssing, fast liste i kode, «Andre» med påkrevd tekst (André,
    19. sep. 2026)."""

    def test_lista_er_den_avtalte(self):
        self.assertEqual([v for v, _ in MELDER_VALG], ['egen', 'amk', 'brann', 'politi', 'lsko', 'andre'])

    def test_kodene_sorteres_i_listas_rekkefoelge_og_dedupliseres(self):
        typer, tekst = services.rens_melder(['andre', 'AMK', 'egen', 'amk'], ' kiosken ')
        self.assertEqual(typer, ['egen', 'amk', 'andre'])
        self.assertEqual(tekst, 'kiosken')

    def test_ukjent_kode_avvises(self):
        with self.assertRaises(services.Ugyldig):
            services.rens_melder(['brann', 'kystvakt'], '')
        with self.assertRaises(services.Ugyldig):
            services.rens_melder('amk', '')

    def test_andre_krever_tekst(self):
        with self.assertRaises(services.Ugyldig):
            services.rens_melder(['andre'], '  ')
        with self.assertRaises(services.Ugyldig):
            self._hendelse(melder_typer=['egen', 'andre'])
        self.assertEqual(Hendelse.objects.count(), 0, 'intet nummer brent')

    def test_tekst_uten_andre_toemmes(self):
        typer, tekst = services.rens_melder(['egen'], 'arrangør')
        self.assertEqual((typer, tekst), (['egen'], ''))

    def test_ikke_oppgitt_roerer_ikke(self):
        typer, tekst = services.rens_melder(None, 'x')
        self.assertIsNone(typer)
        self.assertEqual(tekst, 'x')

    def test_teksten_leses_slik(self):
        h = self._hendelse(melder_typer=['egen', 'lsko'])
        self.assertEqual(services.melder_tekst(h), 'Egen ressurs, LSKO')
        self.assertEqual(services.melder_tekst(self._hendelse()), '')


class LagTests(_Grunnlag):
    """Lagene på hendelsen: vaktlistas ressurser uten enhet, differansen
    logges, lukket hendelse tar ikke imot (André, 19. sep. 2026)."""

    def _koder(self, h):
        return [(l.systemkode, l.systemdata.get('lag'))
                for l in Logglinje.objects.filter(kilde=KILDE_SYSTEM, hendelse=h).order_by('id')]

    def test_lag_ved_opprettelse_staar_paa_opprettelseslinja(self):
        h = self._hendelse(lag=[self.lag1.pk, self.lag2.pk])
        self.assertEqual(h.lag_navn(), ['Lag 1', 'Lag 2'])
        rad = HendelseLag.objects.get(hendelse=h, ressurs=self.lag1)
        self.assertEqual((rad.ressurs_navn, rad.av_navn), ('Lag 1', 'ko1'))
        self.assertIsNotNone(rad.fra)
        koder = self._koder(h)
        self.assertEqual([k for k, _ in koder], [systemlinjer.HENDELSE_OPPRETTET],
                         'én linje, ikke én per lag')
        tekst = systemlinjer.tegn(koder[0][0], Logglinje.objects.get(systemkode=koder[0][0]).systemdata)
        self.assertIn('lag: Lag 1, Lag 2', tekst)

    def test_sett_lag_regner_differansen_og_logger_hver(self):
        h = self._hendelse(lag=[self.lag1.pk])
        lagt_til, tatt_av = services.sett_lag(h, [self.lag2.pk], bruker=self.andre)
        self.assertEqual((lagt_til, tatt_av), (['Lag 2'], ['Lag 1']))
        self.assertEqual(h.lag_navn(), ['Lag 2'])
        koder = self._koder(h)[1:]
        self.assertEqual(koder, [(systemlinjer.HENDELSE_LAG_PAA, 'Lag 2'),
                                 (systemlinjer.HENDELSE_LAG_AV, 'Lag 1')])
        linje = Logglinje.objects.get(systemkode=systemlinjer.HENDELSE_LAG_PAA)
        self.assertEqual(linje.forfatter_navn, 'ko2')
        self.assertIn('Lag 2 registrert på H1', systemlinjer.tegn(linje.systemkode, linje.systemdata))
        self.assertIn('ko2', self._deltakere(h), 'den som registrerer et lag er på hendelsen')

    def test_samme_liste_er_ingen_endring_og_ingen_linje(self):
        h = self._hendelse(lag=[self.lag1.pk])
        foer = Logglinje.objects.count()
        self.assertEqual(services.sett_lag(h, [self.lag1.pk], bruker=self.andre), ([], []))
        self.assertEqual(Logglinje.objects.count(), foer)
        self.assertNotIn('ko2', self._deltakere(h))

    def test_bare_lag_uten_enhet_og_i_lista_i_bruk(self):
        with self.assertRaises(services.Ugyldig):
            self._hendelse(lag=[self.bil.pk])
        annen = Vaktliste.objects.create(vakt=vakt_for_year(2031))
        fremmed = lag_ressurs(vaktliste=annen, navn='Lag X', gruppe=gruppe(LAG))
        with self.assertRaises(services.Ugyldig):
            self._hendelse(lag=[fremmed.pk])
        with self.assertRaises(services.Ugyldig):
            self._hendelse(lag=[999])
        with self.assertRaises(services.Ugyldig):
            self._hendelse(lag='lag1')
        self.assertEqual(Hendelse.objects.count(), 0, 'intet nummer brent')

    def test_lukket_hendelse_tar_ikke_imot(self):
        h = self._hendelse(lag=[self.lag1.pk])
        services.lukk_hendelse(h, bruker=self.operator)
        with self.assertRaises(services.Ugyldig):
            services.sett_lag(h, [], bruker=self.operator)
        self.assertEqual(h.lag_navn(), ['Lag 1'])

    def test_rediger_hendelse_med_lag_gaar_gjennom_sett_lag(self):
        h = self._hendelse()
        services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon, lag=[self.lag2.pk])
        h.refresh_from_db()
        self.assertEqual((h.lag_navn(), h.versjon), (['Lag 2'], 2))
        self.assertEqual(self._koder(h)[-1], (systemlinjer.HENDELSE_LAG_PAA, 'Lag 2'))
        with self.assertRaises(services.Ugyldig):
            services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon, lag=[self.lag2.pk])

    def test_navnet_staar_naar_ressursen_er_borte(self):
        h = self._hendelse(lag=[self.lag1.pk])
        self.lag1.delete()
        self.assertEqual(h.lag_navn(), ['Lag 1'])

    def test_nullstilling_tar_lagene_med(self):
        self._hendelse(lag=[self.lag1.pk])
        services.nullstill_hendelser(self.vakt)
        self.assertEqual(HendelseLag.objects.count(), 0)


class BeskrivelseTests(_Grunnlag):
    """Beskrivelsen er tillegg, aldri overskriving: logglinjer i hendelsen med
    merket, hvem og når — retting og fjerning gjennom loggens regler."""

    def test_tillegg_er_en_linje_i_hendelsen_med_merket(self):
        h = self._hendelse(beskrivelse='første')
        linje = services.legg_til_beskrivelse(h, 'andre', bruker=self.andre)
        self.assertTrue(linje.beskrivelse)
        self.assertEqual(linje.hendelse_id, h.pk)
        self.assertEqual([(t['tekst'], t['av']) for t in h.beskrivelse_tillegg()],
                         [('første', 'ko1'), ('andre', 'ko2')])
        self.assertIn('ko2', self._deltakere(h))

    def test_tillegg_uten_hendelse_avvises(self):
        with self.assertRaises(services.Ugyldig):
            services.skriv_linje(self.vakt, 'x', bruker=self.operator, beskrivelse=True)

    def test_retting_arver_merket_og_hendelsen(self):
        h = self._hendelse(beskrivelse='førstte')
        gammel = Logglinje.objects.get(beskrivelse=True)
        ny = services.korriger(gammel, bruker=self.operator, tekst='første')
        self.assertTrue(ny.beskrivelse)
        self.assertEqual(ny.hendelse_id, h.pk)
        tillegg = h.beskrivelse_tillegg()
        self.assertEqual([t['tekst'] for t in tillegg], ['første'])
        self.assertTrue(tillegg[0]['rettet'])
        self.assertEqual(tillegg[0]['rot'], gammel.pk, 'plassen i rekka er den gamle')

    def test_en_vanlig_kommentar_arver_ogsaa_hendelsen_ved_retting(self):
        """Fantes ikke før 19. sep. 2026: en rettet kommentar i H14 falt ut
        av hendelsen og inn i loggstrømmen."""
        h = self._hendelse()
        linje = services.skriv_linje(self.vakt, 'kommentar', bruker=self.operator, hendelse=h)
        ny = services.korriger(linje, bruker=self.operator, tekst='kommentaren')
        self.assertEqual(ny.hendelse_id, h.pk)
        self.assertFalse(ny.beskrivelse)

    def test_fjernet_tillegg_er_ute_av_rekka(self):
        h = self._hendelse(beskrivelse='første')
        linje = services.legg_til_beskrivelse(h, 'feil', bruker=self.operator)
        services.fjern(linje, bruker=self.operator)
        self.assertEqual([t['tekst'] for t in h.beskrivelse_tillegg()], ['første'])

    def test_rekka_prefetches_i_lista_og_er_den_samme(self):
        h = self._hendelse(beskrivelse='første')
        services.skriv_linje(self.vakt, 'en kommentar', bruker=self.andre, hendelse=h)
        services.legg_til_beskrivelse(h, 'andre', bruker=self.andre)
        fjernet = services.legg_til_beskrivelse(h, 'feil', bruker=self.andre)
        services.fjern(fjernet, bruker=self.operator)
        [rad] = services.hendelser_for(self.vakt)
        self.assertTrue(hasattr(rad, 'tillegg'))
        self.assertEqual([t['tekst'] for t in rad.beskrivelse_tillegg()], ['første', 'andre'],
                         'kommentarer og fjernede tillegg er ikke i rekka')
        self.assertEqual(rad.beskrivelse_tillegg(), h.beskrivelse_tillegg(), 'samme svar med og uten prefetch')

    def test_tom_beskrivelse_gir_ingen_linje(self):
        h = self._hendelse(beskrivelse='  ')
        self.assertEqual(h.beskrivelse_tillegg(), [])
        self.assertEqual(Logglinje.objects.filter(beskrivelse=True).count(), 0)


class KommentarTests(_Grunnlag):
    """En kommentar er en logglinje med hendelsen satt — én tabell."""

    def test_linja_peker_paa_hendelsen(self):
        h = self._hendelse()
        linje = services.skriv_linje(self.vakt, 'melding', bruker=self.operator, hendelse=h)
        self.assertEqual(linje.hendelse_id, h.pk)
        self.assertIn(linje, Logglinje.objects.gjeldende(self.vakt))

    def test_hendelse_i_annen_vakt_avvises(self):
        annen = vakt_for_year(2031)
        h = self._hendelse()
        with self.assertRaises(services.Ugyldig):
            services.skriv_linje(annen, 'melding', bruker=self.operator, hendelse=h)
        self.assertEqual(Logglinje.objects.filter(kilde='operator').count(), 0)

    def test_lukket_hendelse_tar_imot_kommentar(self):
        """En etterskrift etter lukking er lov — loggen er append-only, og
        «pasienten kom hjem» hører til hendelsen selv om den er lukket."""
        h = self._hendelse()
        services.lukk_hendelse(h, bruker=self.operator)
        linje = services.skriv_linje(self.vakt, 'etterskrift', bruker=self.operator, hendelse=h)
        self.assertEqual(linje.hendelse_id, h.pk)


class FestingTests(_Grunnlag):
    """Festede linjer i loggstrømmen: idempotent, aldri systemlinjer, aldri
    fjernede, og navnet fryses."""

    def _linje(self, tekst='beskjed', bruker=None):
        return services.skriv_linje(self.vakt, tekst, bruker=bruker or self.operator)

    def test_fest_og_loesne(self):
        linje = self._linje()
        services.fest_linje(linje, bruker=self.andre)
        linje.refresh_from_db()
        self.assertTrue(linje.er_festet)
        self.assertEqual(linje.festet_av_navn, 'ko2')
        services.losne_linje(linje, bruker=self.operator)
        linje.refresh_from_db()
        self.assertFalse(linje.er_festet)
        self.assertEqual((linje.festet_av_id, linje.festet_av_navn), (None, ''))

    def test_fest_to_ganger_beholder_den_foerste(self):
        linje = self._linje()
        services.fest_linje(linje, bruker=self.operator)
        tid = linje.festet_at
        services.fest_linje(linje, bruker=self.andre)
        linje.refresh_from_db()
        self.assertEqual(linje.festet_at, tid)
        self.assertEqual(linje.festet_av_navn, 'ko1')

    def test_systemlinje_og_fjernet_linje_festes_ikke(self):
        h = self._hendelse()
        system = self._siste_system()
        with self.assertRaises(services.Ugyldig):
            services.fest_linje(system, bruker=self.operator)
        linje = self._linje()
        services.fjern(linje, bruker=self.operator)
        linje.refresh_from_db()
        with self.assertRaises(services.Ugyldig):
            services.fest_linje(linje, bruker=self.operator)

    def test_loesne_en_ufestet_er_ingen_feil(self):
        linje = self._linje()
        services.losne_linje(linje, bruker=self.operator)
        self.assertFalse(linje.er_festet)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(TestCase):
    """Nivåene på de nye stiene, og at `festede` og hodet følger med pollen."""

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.leser = _gi(_bruker('leser'), 'ko', 'les')
        self.skriver = _gi(_bruker('skriver'), 'ko', 'skriv_full')
        self.leder = _gi(_bruker('leder'), 'ko', 'skriv_leder')
        self.sjef = _bruker('sjef', role='admin')
        self.vl = Vaktliste.objects.create(vakt=self.vakt)
        self.lag1 = lag_ressurs(vaktliste=self.vl, navn='Lag 1', gruppe=gruppe(LAG))

    def _post(self, bruker, sti, kropp=None, metode='post'):
        c = Client()
        c.force_login(bruker)
        return getattr(c, metode)(sti, data=json.dumps(kropp or {}), content_type='application/json')

    def _hendelse(self):
        return services.opprett_hendelse(self.vakt, 'H', bruker=self.skriver)

    def test_ny_hendelse_baerer_alle_feltene(self):
        svar = self._post(self.skriver, '/ko/api/hendelser/ny/', {
            'tittel': 'Fall', 'prioritet': 'gul', 'melder_typer': ['andre', 'egen'],
            'melder': 'Lag 1', 'beskrivelse': 'b', 'lag': [self.lag1.pk]})
        self.assertEqual(svar.status_code, 201, svar.content)
        d = svar.json()['data']
        self.assertEqual((d['prioritet'], d['melder_typer'], d['melder']), ('gul', ['egen', 'andre'], 'Lag 1'))
        self.assertEqual(d['melder_tekst'], 'Egen ressurs, Andre (Lag 1)')
        self.assertEqual([(t['tekst'], t['av']) for t in d['beskrivelse']], [('b', 'skriver')])
        self.assertEqual([(l['ressurs_id'], l['navn'], l['av']) for l in d['lag']],
                         [(self.lag1.pk, 'Lag 1', 'skriver')])
        self.assertTrue(d['lag'][0]['fra'])
        self.assertEqual(d['deltakere'], ['skriver'])
        self.assertEqual(d['antall_oppdrag'], 0)

    def test_ukjent_prioritet_melder_og_lag_er_400(self):
        for kropp in ({'tittel': 'x', 'prioritet': 'kritisk'},
                      {'tittel': 'x', 'melder_typer': ['kystvakt']},
                      {'tittel': 'x', 'melder_typer': ['andre']},
                      {'tittel': 'x', 'lag': [999]}):
            with self.subTest(kropp=kropp):
                self.assertEqual(self._post(self.skriver, '/ko/api/hendelser/ny/', kropp).status_code, 400)
        self.assertEqual(Hendelse.objects.count(), 0)

    def test_lagene_settes_med_egen_sti_og_krever_skriv_full(self):
        h = self._hendelse()
        sti = f'/ko/api/hendelser/{h.pk}/lag/'
        self.assertEqual(self._post(self.leser, sti, {'lag': [self.lag1.pk]}).status_code, 403)
        svar = self._post(self.skriver, sti, {'lag': [self.lag1.pk]})
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertEqual([l['navn'] for l in svar.json()['data']['lag']], ['Lag 1'])
        self.assertEqual(self._post(self.skriver, sti, {'lag': [999]}).status_code, 400)
        self.assertEqual(self._post(self.skriver, sti, {}).status_code, 400, 'lista må oppgis')
        svar = self._post(self.skriver, sti, {'lag': []})
        self.assertEqual(svar.json()['data']['lag'], [])
        koder = list(Logglinje.objects.filter(kilde=KILDE_SYSTEM, hendelse=h)
                     .order_by('id').values_list('systemkode', flat=True))
        self.assertEqual(koder[1:], [systemlinjer.HENDELSE_LAG_PAA, systemlinjer.HENDELSE_LAG_AV])

    def test_tillegg_gjennom_loggstien_og_uten_hendelse(self):
        h = self._hendelse()
        svar = self._post(self.skriver, '/ko/api/logg/ny/',
                          {'tekst': 'mer', 'hendelse_id': h.pk, 'beskrivelse': True})
        self.assertEqual(svar.status_code, 201, svar.content)
        self.assertTrue(svar.json()['data']['beskrivelse'])
        self.assertEqual(self._post(self.skriver, '/ko/api/logg/ny/',
                                    {'tekst': 'mer', 'beskrivelse': True}).status_code, 400)
        c = Client(); c.force_login(self.leser)
        [rad] = c.get('/ko/api/logg/').json()['hendelser']
        self.assertEqual([t['tekst'] for t in rad['beskrivelse']], ['mer'])

    def test_prioritet_og_bli_med_krever_skriv_full(self):
        h = self._hendelse()
        for sti, kropp in ((f'/ko/api/hendelser/{h.pk}/prioritet/', {'prioritet': 'rod'}),
                           (f'/ko/api/hendelser/{h.pk}/bli-med/', {})):
            with self.subTest(sti=sti):
                self.assertEqual(self._post(self.leser, sti, kropp).status_code, 403)
                self.assertEqual(self._post(self.skriver, sti, kropp).status_code, 200)

    def test_prioritet_gjennom_api_et(self):
        h = self._hendelse()
        svar = self._post(self.leder, f'/ko/api/hendelser/{h.pk}/prioritet/', {'prioritet': 'viktig'})
        self.assertEqual(svar.json()['data']['prioritet'], 'viktig')
        self.assertIn('leder', svar.json()['data']['deltakere'])
        self.assertEqual(self._post(self.leder, f'/ko/api/hendelser/{h.pk}/prioritet/',
                                    {'prioritet': 'viktig'}).status_code, 400, 'alt satt')

    def test_kommentar_gjennom_api_et_og_utenfor_vakta(self):
        h = self._hendelse()
        svar = self._post(self.skriver, '/ko/api/logg/ny/', {'tekst': 'hei', 'hendelse_id': h.pk})
        self.assertEqual(svar.status_code, 201)
        self.assertEqual(svar.json()['data']['hendelse_id'], h.pk)
        self.assertEqual(self._post(self.skriver, '/ko/api/logg/ny/',
                                    {'tekst': 'hei', 'hendelse_id': 999}).status_code, 404)

    def test_festing_krever_skriv_full_og_pollen_baerer_de_festede(self):
        linje = services.skriv_linje(self.vakt, 'b', bruker=self.skriver)
        self.assertEqual(self._post(self.leser, f'/ko/api/logg/{linje.pk}/fest/').status_code, 403)
        svar = self._post(self.skriver, f'/ko/api/logg/{linje.pk}/fest/')
        self.assertEqual(svar.status_code, 200)
        self.assertTrue(svar.json()['data']['festet_at'])
        c = Client(); c.force_login(self.leser)
        poll = c.get('/ko/api/logg/').json()
        self.assertEqual([f['id'] for f in poll['festede']], [linje.pk])
        self.assertEqual(poll['festede'][0]['festet_av'], 'skriver')
        self._post(self.skriver, f'/ko/api/logg/{linje.pk}/losne/')
        self.assertEqual(c.get('/ko/api/logg/').json()['festede'], [])

    def test_rediger_baerer_melder_og_lag(self):
        h = self._hendelse()
        svar = self._post(self.skriver, f'/ko/api/hendelser/{h.pk}/rediger/', {
            'versjon': h.versjon, 'melder_typer': ['brann'], 'lag': [self.lag1.pk]})
        self.assertEqual(svar.status_code, 200, svar.content)
        d = svar.json()['data']
        self.assertEqual((d['melder_tekst'], [l['navn'] for l in d['lag']]), ('Brann', ['Lag 1']))

    def test_sida_baerer_prioritetene_melderne_og_lagvalget(self):
        c = Client(); c.force_login(self.skriver)
        html = c.get('/ko/').content.decode()
        self.assertIn('data-arg="viktig"', html)
        self.assertIn('id="koHendelseModal"', html)
        self.assertIn('value="lsko"', html)
        self.assertIn('id="ko-h-lag"', html)
        self.assertNotIn('ressursbehov', html.lower())
        c.force_login(self.leser)
        self.assertNotIn('id="koHendelseModal"', c.get('/ko/').content.decode(),
                         'skjemaet finnes ikke for den som ikke kan skrive')

    def test_oppdraget_baerer_hendelsens_prioritet_lag_og_beskrivelse(self):
        """`oppdrag_til_dict` leser dem — det er slik bilen og KO-raden får
        dem — og ETag-en snur når et tillegg kommer til."""
        _gi(self.skriver, 'oppdrag', 'skriv_full')
        h = services.opprett_hendelse(self.vakt, 'H', bruker=self.skriver, prioritet='viktig',
                                      lag=[self.lag1.pk], beskrivelse='første')
        enhet = Enhet.objects.create(navn='HGSD 56', pa_vakt=True)
        lok = Lokasjon.objects.create(navn='Scene')
        o = Oppdrag.objects.create(vakt=self.vakt, oppdragsnummer=1, enhet=enhet, lokasjon=lok,
                                   problemstilling='Fall', hastegrad=choices.HASTEGRAD[0])
        services.knytt_oppdrag(o, h, bruker=self.skriver)
        c = Client(); c.force_login(self.skriver)
        svar = c.get('/oppdrag/api/oppdrag/')
        rad = [r for r in svar.json()['data'] if r['id'] == o.pk][0]
        self.assertEqual((rad['hendelse_prioritet'], rad['hendelse_lag']), ('viktig', ['Lag 1']))
        self.assertEqual([t['tekst'] for t in rad['hendelse_beskrivelse']], ['første'])
        etag = svar['ETag']
        self.assertEqual(c.get('/oppdrag/api/oppdrag/', HTTP_IF_NONE_MATCH=etag).status_code, 304)
        services.legg_til_beskrivelse(h, 'andre', bruker=self.skriver)
        self.assertEqual(c.get('/oppdrag/api/oppdrag/', HTTP_IF_NONE_MATCH=etag).status_code, 200,
                         'et tillegg skal ikke drukne i en 304')

    def test_bilen_mister_beskrivelsen_naar_oppdraget_er_avsluttet(self):
        """Samme regel som friteksten: helseopplysninger skal ikke bli liggende
        i bilen etter at oppdraget er ferdig."""
        from oppdrag.views_common import oppdrag_til_dict
        h = services.opprett_hendelse(self.vakt, 'H', bruker=self.skriver, beskrivelse='pasient')
        enhet = Enhet.objects.create(navn='HGSD 56', pa_vakt=True)
        lok = Lokasjon.objects.create(navn='Scene')
        o = Oppdrag.objects.create(vakt=self.vakt, oppdragsnummer=1, enhet=enhet, lokasjon=lok,
                                   problemstilling='Fall', hastegrad=choices.HASTEGRAD[0],
                                   fritekst='x')
        services.knytt_oppdrag(o, h, bruker=self.skriver)
        self.assertEqual([t['tekst'] for t in oppdrag_til_dict(o, for_enhet=True)['hendelse_beskrivelse']],
                         ['pasient'])
        o.status = choices.TERMINAL
        o.save()
        rad = oppdrag_til_dict(o, for_enhet=True)
        self.assertEqual((rad['hendelse_beskrivelse'], rad['fritekst']), ([], ''))
        self.assertEqual([t['tekst'] for t in oppdrag_til_dict(o)['hendelse_beskrivelse']], ['pasient'],
                         'sentralbordet ser den fortsatt')


class GamleFilerTests(TestCase):
    """En KO-fil fra 18. sep. 2026 bærer `ko.ressursbehov` og tre felter
    som er borte. Den skal fortsatt lastes — 730 dager offsite."""

    def test_utgaatte_felt_og_modeller_tas_ut(self):
        from core.backup import UTGAATTE_FELT, UTGAATTE_MODELLER, fjern_utgaatte
        from django.apps import apps
        for etikett, felter in UTGAATTE_FELT.items():
            modell = apps.get_model(etikett)
            for felt in felter:
                self.assertFalse(any(f.name == felt for f in modell._meta.get_fields()),
                                 f'{etikett}.{felt} finnes fortsatt — da er raden feil')
        for etikett in UTGAATTE_MODELLER:
            app, navn = etikett.split('.')
            self.assertFalse(any(m._meta.model_name == navn for m in apps.get_app_config(app).get_models()),
                             f'{etikett} finnes fortsatt')
        vakt = hent_aktiv_vakt()
        fil = json.dumps([
            {'model': 'ko.ressursbehov', 'pk': 1, 'fields': {'navn': 'Lag', 'er_aktiv': True, 'rekkefolge': 10}},
            {'model': 'ko.hendelse', 'pk': 1, 'fields': {
                'vakt': vakt.pk, 'hendelsesnummer': 7, 'tittel': 'Gammel', 'lokasjon_navn': '',
                'status': 'apen', 'versjon': 1, 'prioritet': 'gronn', 'beskrivelse': 'tekst',
                'melder': 'Lag 1', 'lagsressurser': 'Lag 1, Lag 3', 'ressursbehov': [1],
                'opprettet_at': '2026-09-18T20:00:00Z', 'opprettet_av_navn': 'kari'}},
        ]).encode('utf-8')
        ut = json.loads(fjern_utgaatte(fil))
        self.assertEqual([o['model'] for o in ut], ['ko.hendelse'])
        self.assertNotIn('ressursbehov', ut[0]['fields'])
        self.assertNotIn('beskrivelse', ut[0]['fields'])
        self.assertEqual(ut[0]['fields']['melder'], 'Lag 1')
        # Og det som er igjen lastes faktisk.
        import tempfile
        from django.core import management
        with tempfile.NamedTemporaryFile('wb', suffix='.json', delete=False) as f:
            f.write(json.dumps(ut).encode('utf-8'))
        management.call_command('loaddata', f.name, verbosity=0)
        self.assertEqual(Hendelse.objects.get(pk=1).tittel, 'Gammel')

    def test_en_fil_uten_noe_utgaatt_roeres_ikke(self):
        from core.backup import fjern_utgaatte
        raa = b'[{"model": "ko.logglinje", "pk": 1, "fields": {"tekst": "x"}}]'
        self.assertIs(fjern_utgaatte(raa), raa)


class DatamigrasjonTests(TestCase):
    """`ko/0009`: beskrivelsen ble første tillegg, melder-navnet ble
    «Andre». Prøvd mot dagens modeller gjennom den ekte funksjonen — den
    leser bare felter som finnes i den historiske formen *og* i dag, unntatt
    de to som ble fjernet, og de settes her som attributter."""

    def test_framover(self):
        import importlib
        from django.apps import apps
        modul = importlib.import_module('ko.migrations.0009_beskrivelse_til_tillegg')
        vakt = hent_aktiv_vakt()
        bruker = _bruker('kari')

        class _Apps:
            """`apps.get_model` som gir dagens modeller, med de to gamle
            feltene lagt på som attributter i minnet."""
            @staticmethod
            def get_model(app, navn):
                Modell = apps.get_model(app, navn)
                if navn != 'Hendelse':
                    return Modell
                h = Hendelse.objects.create(vakt=vakt, hendelsesnummer=1, tittel='Gammel',
                                            opprettet_av=bruker, opprettet_av_navn='kari',
                                            melder='Lag 1')
                h.beskrivelse = 'sto i feltet'

                class _Qs(list):
                    def iterator(self):
                        return iter(self)

                class _Mgr:
                    @staticmethod
                    def exclude(**kw):
                        return _Qs([h])

                class _H:
                    objects = _Mgr()
                return _H

        modul.framover(_Apps, None)
        h = Hendelse.objects.get()
        self.assertEqual([(t['tekst'], t['av']) for t in h.beskrivelse_tillegg()], [('sto i feltet', 'kari')])
        self.assertEqual(h.beskrivelse_tillegg()[0]['tid'], h.opprettet_at.isoformat())
        self.assertEqual(h.melder_typer, ['andre'])
