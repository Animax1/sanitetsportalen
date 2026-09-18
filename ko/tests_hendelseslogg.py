"""Hendelsesloggen som egen flate (18. sep. 2026): prioritet, «bli med»,
festing, ressursbehovene og feltene i hodet — reglene og portene.

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
from ko.models import (KILDE_SYSTEM, PRIORITET_GRONN, PRIORITET_RANG,
                       PRIORITET_VALG, PRIORITET_VIKTIG, Hendelse,
                       HendelseDeltaker, Logglinje, Ressursbehov)
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
        self.andre = _bruker('ko2')
        self.enhet = Enhet.objects.create(navn='HGSD 56')
        self.lokasjon = Lokasjon.objects.create(navn='Scene sør')
        self.amb = Ressursbehov.objects.create(navn='Ambulanse', rekkefolge=10)
        self.lag = Ressursbehov.objects.create(navn='Lag', rekkefolge=20)

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
        services.rediger_hendelse(h, bruker=tredje, versjon=h.versjon, melder='Lag 2')
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
    """Beskrivelse, melder, lagsressurser og ressursbehov: valideres før
    nummeret trekkes, redigeres med versjon."""

    def test_feltene_lagres_ved_opprettelse(self):
        h = self._hendelse(beskrivelse=' Mann ca. 40 ', melder='Lag 1',
                           lokasjon=self.lokasjon, ressursbehov=[self.amb.pk, self.lag.pk])
        self.assertEqual(h.beskrivelse, 'Mann ca. 40')
        self.assertEqual(h.melder, 'Lag 1')
        self.assertEqual(sorted(h.ressursbehov.values_list('navn', flat=True)), ['Ambulanse', 'Lag'])
        self.assertEqual(h.lokasjon_navn, 'Scene sør')

    def test_for_lange_felt_avvises_foer_nummeret_trekkes(self):
        """Telleren lar seg ikke rulle tilbake av en 400 — en avvist
        innsending som alt hadde hentet H14 ville etterlatt et hull."""
        for felt, verdi in (('beskrivelse', 'x' * (services.MAKS_BESKRIVELSE + 1)),
                            ('melder', 'x' * (services.MAKS_MELDER + 1))):
            with self.subTest(felt=felt):
                with self.assertRaises(services.Ugyldig):
                    self._hendelse(**{felt: verdi})
        self.assertEqual(Hendelse.objects.count(), 0)
        h = self._hendelse()
        self.assertEqual(h.hendelsesnummer, 1, 'ingen nummer brent')

    def test_grensene_selv_er_lov(self):
        h = self._hendelse(beskrivelse='x' * services.MAKS_BESKRIVELSE,
                           melder='x' * services.MAKS_MELDER)
        self.assertEqual(len(h.beskrivelse), services.MAKS_BESKRIVELSE)

    def test_ukjent_ressursbehov_er_400_ikke_stille_utelatt(self):
        with self.assertRaises(services.Ugyldig):
            self._hendelse(ressursbehov=[self.amb.pk, 999])
        with self.assertRaises(services.Ugyldig):
            self._hendelse(ressursbehov='amb')
        with self.assertRaises(services.Ugyldig):
            self._hendelse(ressursbehov=['x'])
        self.assertEqual(Hendelse.objects.count(), 0)

    def test_rediger_hvert_felt(self):
        h = self._hendelse()
        services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon,
                                  beskrivelse='ny', melder='publikum',
                                  lagsressurser='Lag 1, Lag 3',
                                  ressursbehov=[self.lag.pk])
        h.refresh_from_db()
        self.assertEqual((h.beskrivelse, h.melder, h.lagsressurser), ('ny', 'publikum', 'Lag 1, Lag 3'))
        self.assertEqual(list(h.ressursbehov.values_list('pk', flat=True)), [self.lag.pk])
        self.assertEqual(h.versjon, 2)

    def test_tom_streng_toemmer_none_roerer_ikke(self):
        h = self._hendelse(melder='Lag 1', beskrivelse='b')
        services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon, melder='')
        h.refresh_from_db()
        self.assertEqual(h.melder, '')
        self.assertEqual(h.beskrivelse, 'b')

    def test_ressursbehov_uendret_er_ingen_endring(self):
        h = self._hendelse(ressursbehov=[self.amb.pk])
        with self.assertRaises(services.Ugyldig):
            services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon,
                                      ressursbehov=[self.amb.pk])
        h.refresh_from_db()
        self.assertEqual(h.versjon, 1)

    def test_ressursbehov_alene_er_en_endring(self):
        h = self._hendelse(ressursbehov=[self.amb.pk])
        services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon, ressursbehov=[])
        h.refresh_from_db()
        self.assertEqual(h.ressursbehov.count(), 0)
        self.assertEqual(h.versjon, 2)

    def test_lagsressurser_for_lange_avvises(self):
        h = self._hendelse()
        with self.assertRaises(services.Ugyldig):
            services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon,
                                      lagsressurser='x' * (services.MAKS_LAGSRESSURSER + 1))

    def test_versjonen_kreves_fortsatt(self):
        h = self._hendelse()
        with self.assertRaises(services.Konflikt):
            services.rediger_hendelse(h, bruker=self.operator, versjon=h.versjon + 1, melder='x')


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
        self.amb = Ressursbehov.objects.create(navn='Ambulanse')

    def _post(self, bruker, sti, kropp=None, metode='post'):
        c = Client()
        c.force_login(bruker)
        return getattr(c, metode)(sti, data=json.dumps(kropp or {}), content_type='application/json')

    def _hendelse(self):
        return services.opprett_hendelse(self.vakt, 'H', bruker=self.skriver)

    def test_ny_hendelse_baerer_alle_feltene(self):
        svar = self._post(self.skriver, '/ko/api/hendelser/ny/', {
            'tittel': 'Fall', 'prioritet': 'gul', 'melder': 'Lag 1',
            'beskrivelse': 'b', 'ressursbehov': [self.amb.pk]})
        self.assertEqual(svar.status_code, 201, svar.content)
        d = svar.json()['data']
        self.assertEqual((d['prioritet'], d['melder'], d['beskrivelse']), ('gul', 'Lag 1', 'b'))
        self.assertEqual(d['ressursbehov'], [{'id': self.amb.pk, 'navn': 'Ambulanse'}])
        self.assertEqual(d['deltakere'], ['skriver'])
        self.assertEqual(d['lagsressurser'], '')
        self.assertEqual(d['antall_oppdrag'], 0)

    def test_ukjent_prioritet_og_ressursbehov_er_400(self):
        self.assertEqual(self._post(self.skriver, '/ko/api/hendelser/ny/',
                                    {'tittel': 'x', 'prioritet': 'kritisk'}).status_code, 400)
        self.assertEqual(self._post(self.skriver, '/ko/api/hendelser/ny/',
                                    {'tittel': 'x', 'ressursbehov': [999]}).status_code, 400)

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

    def test_rediger_baerer_de_nye_feltene(self):
        h = self._hendelse()
        svar = self._post(self.skriver, f'/ko/api/hendelser/{h.pk}/rediger/', {
            'versjon': h.versjon, 'lagsressurser': 'Lag 1', 'melder': 'Lag 2'})
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertEqual(svar.json()['data']['lagsressurser'], 'Lag 1')

    def test_ressursbehov_settes_opp_av_ko_leder_eller_admin(self):
        """Lista: `les`. Opprett/endre/rekkefølge: `skriv_leder` i KO, eller
        global admin. Sletting: global admin, og bare ubrukte."""
        c = Client(); c.force_login(self.leser)
        self.assertEqual(c.get('/ko/api/ressursbehov/').status_code, 200)
        self.assertEqual(self._post(self.skriver, '/ko/api/ressursbehov/', {'navn': 'Lag'}).status_code, 403)
        svar = self._post(self.leder, '/ko/api/ressursbehov/', {'navn': 'Lag'})
        self.assertEqual(svar.status_code, 200, svar.content)
        pk = svar.json()['data']['id']
        self.assertEqual(self._post(self.leder, '/ko/api/ressursbehov/', {'navn': 'Lag'}).status_code, 400, 'finnes alt')
        self.assertEqual(self._post(self.leder, '/ko/api/ressursbehov/', {'navn': ''}).status_code, 400)
        self.assertEqual(self._post(self.leder, f'/ko/api/ressursbehov/{pk}/',
                                    {'er_aktiv': False}, 'put').status_code, 200)
        self.assertFalse(Ressursbehov.objects.get(pk=pk).er_aktiv)
        self.assertEqual(self._post(self.leder, '/ko/api/ressursbehov/rekkefolge/',
                                    {'ider': [pk, self.amb.pk]}, 'put').status_code, 200)
        self.assertLess(Ressursbehov.objects.get(pk=pk).rekkefolge,
                        Ressursbehov.objects.get(pk=self.amb.pk).rekkefolge)
        # Sletting
        self.assertEqual(self._post(self.leder, f'/ko/api/ressursbehov/{pk}/', {'confirm': True}, 'delete').status_code, 403)
        self.assertEqual(self._post(self.sjef, f'/ko/api/ressursbehov/{pk}/', {}, 'delete').status_code, 400, 'confirm')
        h = self._hendelse()
        h.ressursbehov.add(self.amb)
        self.assertEqual(self._post(self.sjef, f'/ko/api/ressursbehov/{self.amb.pk}/', {'confirm': True}, 'delete').status_code, 409, 'i bruk')
        self.assertEqual(self._post(self.sjef, f'/ko/api/ressursbehov/{pk}/', {'confirm': True}, 'delete').status_code, 200)
        self.assertFalse(Ressursbehov.objects.filter(pk=pk).exists())

    def test_sida_baerer_prioritetene_og_ressursbehovene(self):
        c = Client(); c.force_login(self.skriver)
        html = c.get('/ko/').content.decode()
        self.assertIn('data-arg="viktig"', html)
        self.assertIn('id="koHendelseModal"', html)
        self.assertIn('Ambulanse', html)
        c.force_login(self.leser)
        self.assertNotIn('id="koHendelseModal"', c.get('/ko/').content.decode(),
                         'skjemaet finnes ikke for den som ikke kan skrive')

    def test_oppdraget_baerer_hendelsens_prioritet_og_lag(self):
        """`oppdrag_til_dict` leser dem — det er slik bilen og KO-raden får dem."""
        _gi(self.skriver, 'oppdrag', 'skriv_full')
        h = services.opprett_hendelse(self.vakt, 'H', bruker=self.skriver, prioritet='viktig')
        services.rediger_hendelse(h, bruker=self.skriver, versjon=h.versjon, lagsressurser='Lag 1')
        enhet = Enhet.objects.create(navn='HGSD 56', pa_vakt=True)
        lok = Lokasjon.objects.create(navn='Scene')
        o = Oppdrag.objects.create(vakt=self.vakt, oppdragsnummer=1, enhet=enhet, lokasjon=lok,
                                   problemstilling='Fall', hastegrad=choices.HASTEGRAD[0])
        services.knytt_oppdrag(o, h, bruker=self.skriver)
        c = Client(); c.force_login(self.skriver)
        rad = [r for r in c.get('/oppdrag/api/oppdrag/').json()['data'] if r['id'] == o.pk][0]
        self.assertEqual((rad['hendelse_prioritet'], rad['hendelse_lagsressurser']), ('viktig', 'Lag 1'))
