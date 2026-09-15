# -*- coding: utf-8 -*-
"""Planleggeren: grunnlaget for vaktlista (15. sep. 2026).

André: «En planlegger-fane i /vaktlisten … Den skal bare admin og leder ha
tilgang til. For den genererer grunnlaget på alt. Vi skal kunne legge inn skift
f.eks. tre firemanns lag fra kl. 14–22 og en ambulanse fra 15–03 mens en
ambulanse går 8 timer rotasjon. Den skal sette opp planen som lager grunnlaget
for vaktlisten. Så skal vi kunne fordele vaktene og etterhvert spisse de inn.»

**Hans tre eksempler er grunnstammen her**, regnet ut i tall:

| Oppsett | Blir |
|---|---|
| 3 lag à 4 plasser, fre. 14–22 | 3 ressurser, 12 plasser, 96 t |
| Haugesund 56: seks vinduer à 8 t, 2 plasser hvert | 12 plasser, 96 t |
| Sola 56: to vinduer fre./lør. 15–03, 2 plasser | 4 plasser, 48 t |

Det siste er grunnen til at **ressursen er subjektet og vinduene hører til
den**: var linja enheten, hadde Sola 56 blitt to ulike biler.

**Ett vindu er ett skift** (15. sep. 2026). `skiftlengde`, som delte vinduet i
bolker, er fjernet — den var en skjult multiplikator der alle de genererte
skiftene fikk samme antall plasser, og det er nettopp det som ikke lot seg
uttrykke da plassene ble flyttet til vinduet.

**Plassene hører til vinduet**, ikke til ressursen: samleplassen kan ha seks
14–22 og to 22–06.
"""
import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from django.utils import timezone

from . import services
from .models import Ressurs, Vaktpost
from .test_helpers import gruppe
from .tests_tilgang import TilgangsBasis

OSLO = ZoneInfo('Europe/Oslo')


def kl(dag, time, minutt=0):
    """Et tidspunkt i **norsk** tid, båret som UTC — som ORM-en gjør."""
    return datetime(2026, 10, dag, time, minutt,
                    tzinfo=OSLO).astimezone(dt_timezone.utc)


class SkiftvinduValideringTests(TilgangsBasis):
    """Vinduets egne krav. `SkiftvinduTests` målte rotasjonen, som er borte."""

    def _skift(self, fra, til, plasser=2):
        return services._linjens_skift({'vinduer': [
            {'fra': fra, 'til': til, 'plasser': plasser}]})

    def test_ett_vindu_er_ett_skift(self):
        """Regelen etter at `skiftlengde` ble fjernet: et vindu deles ikke."""
        skift = self._skift(kl(2, 14), kl(4, 14))
        self.assertEqual(1, len(skift), '48 timer er fortsatt ett skift')
        self.assertEqual((kl(2, 14), kl(4, 14), 2), skift[0])

    def test_plassene_foelger_vinduet(self):
        self.assertEqual(6, self._skift(kl(2, 14), kl(2, 22), 6)[0][2])

    def test_ulike_vinduer_kan_ha_ulikt_antall(self):
        """André: «noen ganger ønsker man å ha mindre og mer plasser på
        enkelte skift visse deler av døgnet.»"""
        skift = services._linjens_skift({'vinduer': [
            {'fra': kl(2, 14), 'til': kl(2, 22), 'plasser': 6},
            {'fra': kl(2, 22), 'til': kl(3, 6), 'plasser': 2},
        ]})
        self.assertEqual([6, 2], [pl for _, _, pl in skift])

    def test_bakvendt_vindu_avvises(self):
        with self.assertRaises(services.Planleggerfeil):
            self._skift(kl(3, 3), kl(2, 15))

    def test_null_lengde_vindu_avvises(self):
        with self.assertRaises(services.Planleggerfeil):
            self._skift(kl(2, 15), kl(2, 15))

    def test_vindu_uten_tid_avvises(self):
        with self.assertRaises(services.Planleggerfeil):
            self._skift(None, kl(2, 22))

    def test_null_plasser_avvises(self):
        with self.assertRaises(services.Planleggerfeil):
            self._skift(kl(2, 14), kl(2, 22), 0)

    def test_ressurs_uten_vindu_avvises(self):
        with self.assertRaises(services.Planleggerfeil):
            services._linjens_skift({'vinduer': []})


class GrunnlagTests(TilgangsBasis):
    """`generer_grunnlag` mot basen — Andrés tre eksempler."""

    def _lag(self, gruppenavn, antall, plasser, *vinduer):
        """**Plassene ligger på vinduet** (15. sep. 2026). Hjelperen tar dem
        fortsatt som ett argument fordi de fleste oppsettene har samme antall
        hele veien; `_ulike()` under er formen når de varierer."""
        return {'gruppe_id': gruppe(gruppenavn).pk, 'antall': antall,
                'vinduer': [{'fra': f, 'til': t, 'skiftlengde': s,
                             'plasser': plasser}
                            for f, t, s in vinduer]}

    def _ulike(self, gruppenavn, *vinduer):
        """Ett vindu per rad, med sitt eget antall plasser."""
        return {'gruppe_id': gruppe(gruppenavn).pk, 'antall': 1,
                'vinduer': [{'fra': f, 'til': t, 'skiftlengde': s,
                             'plasser': pl}
                            for f, t, s, pl in vinduer]}

    def _ny_liste(self):
        """En **tom** liste. `TilgangsBasis` har alt ressurser på `self.vl`,
        og planleggeren skal prøves der den brukes: på en tom vakt."""
        return services.opprett_planlagt_vakt('Planlagt vakt')

    def _poster(self, vl):
        return Vaktpost.objects.filter(ressurs__vaktliste=vl)

    def test_tre_firemannslag_fra_14_til_22(self):
        vl = self._ny_liste()
        svar = services.generer_grunnlag(
            vl, [self._lag('Lag', 3, 4, (kl(2, 14), kl(2, 22), None))])
        self.assertEqual(3, svar['ressurser'])
        self.assertEqual(12, svar['plasser'])
        self.assertEqual(96.0, svar['timer'])
        self.assertEqual(['Lag 1', 'Lag 2', 'Lag 3'],
                         sorted(Ressurs.objects.filter(vaktliste=vl)
                                .values_list('navn', flat=True)))
        self.assertEqual(12, self._poster(vl).count())

    def test_haugesund_56_gaar_atte_timers_rotasjon(self):
        """Kontinuerlig vakt fre. 14 → søn. 14, bemannet av to lag som går
        åtte på og åtte av. Bilen har **to plasser** — de fire er
        bemanningspoolen, ikke seter.

        Etter at `skiftlengde` ble fjernet settes rotasjonen opp som de seks
        skiftene den er. «Nytt skiftvindu» begynner der det forrige sluttet,
        så det er seks klikk — og nå kan natta settes til færre plasser."""
        vl = self._ny_liste()
        vinduer = [(kl(2, 14) + timedelta(hours=8 * i),
                    kl(2, 14) + timedelta(hours=8 * (i + 1)), None)
                   for i in range(6)]
        svar = services.generer_grunnlag(
            vl, [self._lag('Ambulanse', 1, 2, *vinduer)])
        self.assertEqual(1, svar['ressurser'])
        self.assertEqual(12, svar['plasser'], '6 skift × 2 plasser')
        self.assertEqual(96.0, svar['timer'])
        tider = sorted(set(self._poster(vl).values_list('fra_tid', flat=True)))
        self.assertEqual(6, len(tider), 'seks skiftvinduer')

    def test_samleplassen_kan_ha_faerre_plasser_om_natta(self):
        """Bestillingen bak flyttingen (André, 15. sep. 2026). Seks 14–22 og
        to 22–06 er **én** samleplass med to vinduer."""
        vl = self._ny_liste()
        svar = services.generer_grunnlag(vl, [self._ulike(
            'Samleplass',
            (kl(2, 14), kl(2, 22), None, 6),
            (kl(2, 22), kl(3, 6), None, 2))])
        self.assertEqual(1, svar['ressurser'])
        self.assertEqual(8, svar['plasser'])
        self.assertEqual(64.0, svar['timer'], '6 × 8 t + 2 × 8 t')
        self.assertEqual(['Samleplass'],
                         list(Ressurs.objects.filter(vaktliste=vl)
                              .values_list('navn', flat=True)))

    def test_sola_56_faar_to_adskilte_tolvtimersvakter(self):
        """**To vinduer på én ressurs**, ikke to biler. Det er hele grunnen
        til at ressursen er subjektet i oppsettet."""
        vl = self._ny_liste()
        svar = services.generer_grunnlag(vl, [self._lag(
            'Ambulanse', 1, 2,
            (kl(2, 15), kl(3, 3), None),
            (kl(3, 15), kl(4, 3), None))])
        self.assertEqual(1, svar['ressurser'], 'én bil, ikke to')
        self.assertEqual(4, svar['plasser'])
        self.assertEqual(48.0, svar['timer'])
        self.assertEqual(1, Ressurs.objects.filter(vaktliste=vl).count())

    def test_hele_oppsettet_i_en_omgang(self):
        """Alle tre linjene sammen — det er slik fanen brukes."""
        vl = self._ny_liste()
        svar = services.generer_grunnlag(vl, [
            self._lag('Lag', 3, 4, (kl(2, 14), kl(2, 22), None)),
            self._lag('Ambulanse', 1, 2,
                      *[(kl(2, 14) + timedelta(hours=8 * i),
                         kl(2, 14) + timedelta(hours=8 * (i + 1)), None)
                        for i in range(6)]),
            self._lag('Ambulanse', 1, 2,
                      (kl(2, 15), kl(3, 3), None),
                      (kl(3, 15), kl(4, 3), None)),
        ])
        self.assertEqual(5, svar['ressurser'])
        self.assertEqual(28, svar['plasser'])
        self.assertEqual(240.0, svar['timer'])
        self.assertEqual(['Ambulanse 1', 'Ambulanse 2',
                          'Lag 1', 'Lag 2', 'Lag 3'],
                         sorted(Ressurs.objects.filter(vaktliste=vl)
                                .values_list('navn', flat=True)))

    def test_plassene_fodes_som_planlagt_kladd(self):
        """Beslutning 10. Uten det ser et halvferdig oppsett ferdig ut for
        alle korps i det øyeblikket generatoren kjører."""
        vl = self._ny_liste()
        services.generer_grunnlag(
            vl, [self._lag('Lag', 1, 2, (kl(2, 14), kl(2, 22), None))])
        for vp in self._poster(vl).select_related('ressurs'):
            self.assertTrue(services.er_planlagt(vp))
            self.assertIsNone(vp.mannskap_id)

    def test_forhaandsvisningen_skriver_ingenting(self):
        vl = self._ny_liste()
        linjer = [self._lag('Lag', 3, 4, (kl(2, 14), kl(2, 22), None))]
        svar = services.forhaandsvis_grunnlag(vl, linjer)
        self.assertEqual(12, svar['plasser'])
        self.assertEqual(0, Ressurs.objects.filter(vaktliste=vl).count())
        self.assertEqual(0, self._poster(vl).count())

    def test_forhaandsvisningen_sier_det_samme_som_genereringen(self):
        """Regnes de hver for seg, viser de før eller siden ulike ting."""
        vl = self._ny_liste()
        linjer = [
            self._lag('Lag', 2, 4, (kl(2, 14), kl(2, 22), None)),
            self._lag('Ambulanse', 1, 2, (kl(2, 14), kl(4, 14), 8)),
        ]
        foer = services.forhaandsvis_grunnlag(vl, linjer)
        etter = services.generer_grunnlag(vl, linjer)
        for nokkel in ('ressurser', 'plasser', 'timer'):
            self.assertEqual(foer[nokkel], etter[nokkel], nokkel)
        self.assertEqual([r['navn'] for r in foer['linjer']],
                         [r['navn'] for r in etter['linjer']],
                         'navnene i svaret skal være dem som ble laget')

    def test_navnene_teller_videre_fra_det_som_staar_der(self):
        vl = self._ny_liste()
        services.generer_grunnlag(
            vl, [self._lag('Lag', 2, 2, (kl(2, 14), kl(2, 22), None))])
        services.generer_grunnlag(
            vl, [self._lag('Lag', 1, 2, (kl(2, 14), kl(2, 22), None))])
        self.assertEqual(['Lag 1', 'Lag 2', 'Lag 3'],
                         sorted(Ressurs.objects.filter(vaktliste=vl)
                                .values_list('navn', flat=True)))

    def test_navnene_teller_forbi_hull(self):
        """Står «Lag 1» og «Lag 3», blir den neste «Lag 2». Nummeret er en
        etikett, ikke en ID, og hullet er noe man har laget ved å slette."""
        vl = self._ny_liste()
        Ressurs.objects.create(vaktliste=vl, navn='Lag 1',
                               gruppe=gruppe('Lag'))
        Ressurs.objects.create(vaktliste=vl, navn='Lag 3',
                               gruppe=gruppe('Lag'))
        services.generer_grunnlag(
            vl, [self._lag('Lag', 1, 1, (kl(2, 14), kl(2, 22), None))])
        self.assertTrue(
            Ressurs.objects.filter(vaktliste=vl, navn='Lag 2').exists())

    def test_gruppe_i_ett_eksemplar_faar_navnet_bart(self):
        """«Samleplass», ikke «Samleplass 1» — det finnes ingen nummer to."""
        vl = self._ny_liste()
        services.generer_grunnlag(
            vl, [self._lag('Samleplass', 1, 4, (kl(2, 14), kl(2, 22), None))])
        self.assertEqual(['Samleplass'],
                         list(Ressurs.objects.filter(vaktliste=vl)
                              .values_list('navn', flat=True)))

    def test_gruppe_i_ett_eksemplar_kan_ikke_bestilles_i_flere(self):
        """Samme regel som `ressurser_view`, og den må stå her også: en
        generator som lager «Samleplass 2» er akkurat den feilen
        `flere_enheter` finnes for."""
        vl = self._ny_liste()
        with self.assertRaises(services.Planleggerfeil):
            services.generer_grunnlag(
                vl, [self._lag('Samleplass', 2, 4,
                               (kl(2, 14), kl(2, 22), None))])

    def test_gruppe_i_ett_eksemplar_som_alt_staar_der_avvises(self):
        vl = self._ny_liste()
        linje = self._lag('KO', 1, 2, (kl(2, 14), kl(2, 22), None))
        services.generer_grunnlag(vl, [linje])
        with self.assertRaises(services.Planleggerfeil):
            services.generer_grunnlag(vl, [linje])

    def test_ingenting_skrives_naar_en_senere_linje_feiler(self):
        """`transaction.atomic` rundt hele genereringen. Et halvt grunnlag
        er verre enn ingenting: man ser ressurser stå der og tror det gikk."""
        vl = self._ny_liste()
        with self.assertRaises(services.Planleggerfeil):
            services.generer_grunnlag(vl, [
                self._lag('Lag', 2, 4, (kl(2, 14), kl(2, 22), None)),
                self._lag('Samleplass', 3, 4, (kl(2, 14), kl(2, 22), None)),
            ])
        self.assertEqual(0, Ressurs.objects.filter(vaktliste=vl).count())
        self.assertEqual(0, self._poster(vl).count())

    def test_tomt_oppsett_avvises(self):
        with self.assertRaises(services.Planleggerfeil):
            services.generer_grunnlag(self._ny_liste(), [])

    def test_ressurs_uten_vindu_avvises(self):
        vl = self._ny_liste()
        with self.assertRaises(services.Planleggerfeil):
            services.generer_grunnlag(
                vl, [{'gruppe_id': gruppe('Lag').pk, 'antall': 1,
                      'vinduer': []}])

    def test_ukjent_gruppe_avvises(self):
        vl = self._ny_liste()
        with self.assertRaises(services.Planleggerfeil):
            services.generer_grunnlag(
                vl, [{'gruppe_id': 999999, 'antall': 1,
                      'vinduer': [{'fra': kl(2, 14), 'til': kl(2, 22),
                                   'skiftlengde': None, 'plasser': 1}]}])

    def test_altfor_stort_oppsett_avvises_framfor_aa_skrives(self):
        """Sperra er mot et uhell man må rydde opp i for hånd, ikke en regel
        om hvor stor en vakt kan være."""
        vl = self._ny_liste()
        with self.assertRaises(services.Planleggerfeil):
            services.generer_grunnlag(
                vl, [self._lag('Lag', 50, 50, (kl(2, 0), kl(3, 0), None))])
        self.assertEqual(0, Ressurs.objects.filter(vaktliste=vl).count())

    def test_ressursene_faar_fanerekkefolge_i_den_rekkefolgen_de_kom(self):
        vl = self._ny_liste()
        services.generer_grunnlag(vl, [
            self._lag('Lag', 2, 2, (kl(2, 14), kl(2, 22), None)),
            self._lag('Ambulanse', 1, 2, (kl(2, 14), kl(2, 22), None)),
        ])
        rekke = list(Ressurs.objects.filter(vaktliste=vl)
                     .order_by('rekkefolge').values_list('navn', flat=True))
        self.assertEqual(['Lag 1', 'Lag 2', 'Ambulanse 1'], rekke)

    def test_plassene_faar_ingen_rolle(self):
        """Beslutning: bare antall — roller settes etterpå, i raden der man
        uansett ser hvem som står der."""
        vl = self._ny_liste()
        services.generer_grunnlag(
            vl, [self._lag('Lag', 1, 4, (kl(2, 14), kl(2, 22), None))])
        for vp in self._poster(vl):
            self.assertIsNone(vp.rolle_id)


class ErstattKladdTests(TilgangsBasis):
    """Beslutning 4 og 11: en ny generering rører **bare** kladden."""

    def setUp(self):
        super().setUp()
        self.vl2 = services.opprett_planlagt_vakt('Planlagt vakt')
        self.res = Ressurs.objects.create(
            vaktliste=self.vl2, navn='Lag 1', gruppe=gruppe('Lag'))

    def _plass(self, **felt):
        return Vaktpost.objects.create(
            ressurs=self.res, fra_tid=kl(2, 14), til_tid=kl(2, 22), **felt)

    def _linje(self):
        return {'gruppe_id': gruppe('Lag').pk, 'antall': 1,
                'vinduer': [{'fra': kl(3, 14), 'til': kl(3, 22),
                             'skiftlengde': None, 'plasser': 1}]}

    def _generer(self):
        return services.generer_grunnlag(
            self.vl2, [self._linje()], erstatt_kladd=True)

    def test_kladd_erstattes(self):
        """En tom plass uten reservasjon er generatorens eget utkast, og å
        skrive over sitt eget utkast koster ingenting."""
        kladd = self._plass()
        self.assertTrue(services.er_planlagt(kladd))
        svar = self._generer()
        self.assertEqual(1, svar['slettet'])
        self.assertFalse(Vaktpost.objects.filter(pk=kladd.pk).exists())

    def test_korpsreservert_plass_beholdes(self):
        """Et løfte til et korps: de ser den i «Mitt korps» og planlegger mot
        den. Å slette den er å trekke tilbake en tildeling."""
        reservert = self._plass(korps=self.hgsd)
        self._generer()
        self.assertTrue(Vaktpost.objects.filter(pk=reservert.pk).exists())

    def test_plass_apen_for_alle_beholdes(self):
        """Beslutning 11. `alle_korps` er også en utdeling."""
        apen = self._plass(alle_korps=True)
        self._generer()
        self.assertTrue(Vaktpost.objects.filter(pk=apen.pk).exists())

    def test_plass_reservert_gjennom_ressursen_beholdes(self):
        """Reservasjonen leses av `reservert_korps()`, ikke av feltet:
        plassens egen `korps` overstyrer ressursens, og tom verdi betyr «som
        ressursen». Leses feltet direkte, slettes hele bilens plasser."""
        self.res.korps = self.hgsd
        self.res.save(update_fields=['korps'])
        arvet = self._plass()
        self.assertFalse(services.er_planlagt(arvet))
        self._generer()
        self.assertTrue(Vaktpost.objects.filter(pk=arvet.pk).exists())

    def test_bemannet_plass_beholdes_alltid(self):
        bemannet = self._plass(mannskap=self.p_hgsd)
        self._generer()
        self.assertTrue(Vaktpost.objects.filter(pk=bemannet.pk).exists())

    def test_uten_erstatt_slettes_ingenting(self):
        kladd = self._plass()
        svar = services.generer_grunnlag(self.vl2, [self._linje()])
        self.assertEqual(0, svar['slettet'])
        self.assertTrue(Vaktpost.objects.filter(pk=kladd.pk).exists())

    def test_kladd_paa_en_annen_vaktliste_roeres_ikke(self):
        """Genereringen er scopet til lista. Uten det ville en generering på
        oktobervakta ryddet i septembervakta.

        **Plassen må være ekte kladd for at testen skal måle noe.**
        Mutasjonsprøvd 15. sep. 2026: den sto først på `res_hgsd`, som er
        reservert til Haugesund — altså beholdt uansett, og en generering
        uten scope gikk grønn. `res_fri` (KO) er ureservert, så plassen er
        kladd og ville blitt slettet."""
        annen = Vaktpost.objects.create(
            ressurs=self.res_fri, fra_tid=kl(2, 14), til_tid=kl(2, 22))
        self.assertTrue(services.er_planlagt(annen),
                        'plassen må være kladd, ellers måler testen ingenting')
        self._generer()
        self.assertTrue(Vaktpost.objects.filter(pk=annen.pk).exists())

    def test_slettet_kladd_kommer_tilbake_naar_skrivingen_feiler(self):
        """**Transaksjonen er ikke pynt her.** `erstatt_kladd` sletter først
        og skriver så; feiler skrivingen halvveis uten savepoint, står man
        igjen med en liste der kladden er borte og ingenting kom i stedet —
        altså verre enn før man trykket.

        Mutasjonsprøvd: `transaction.atomic()` lot seg fjerne uten at noe ble
        rødt, fordi all validering skjer i `_planlegg` *før* skrivingen. Det
        som mangler er en feil som inntreffer underveis."""
        from unittest.mock import patch
        kladd = self._plass()
        ekte = Ressurs.objects.create

        kall = {'n': 0}

        def feiler(*args, **kwargs):
            kall['n'] += 1
            if kall['n'] >= 2:
                raise RuntimeError('basen falt ut midt i skrivingen')
            return ekte(*args, **kwargs)

        linjer = [self._linje(), self._linje()]
        with patch.object(Ressurs.objects, 'create', side_effect=feiler):
            with self.assertRaises(RuntimeError):
                services.generer_grunnlag(self.vl2, linjer,
                                          erstatt_kladd=True)

        self.assertTrue(Vaktpost.objects.filter(pk=kladd.pk).exists(),
                        'kladden skal stå der som før')
        self.assertEqual(1, Ressurs.objects.filter(vaktliste=self.vl2).count(),
                         'bare ressursen fra setUp skal stå igjen')


class PlanleggerApiTests(TilgangsBasis):
    """Endepunktet, og porten foran det."""

    def setUp(self):
        super().setUp()
        self.vl2 = services.opprett_planlagt_vakt('Planlagt vakt')

    def _kall(self, klient, **kropp):
        kropp.setdefault('linjer', [{
            'gruppe_id': gruppe('Lag').pk, 'antall': 1,
            'vinduer': [{'fra': kl(2, 14).isoformat(),
                         'til': kl(2, 22).isoformat(), 'skiftlengde': None,
                         'plasser': 2}]}])
        return klient.post(
            f'/vaktliste/api/vaktlister/{self.vl2.pk}/generer/',
            data=json.dumps(kropp), content_type='application/json')

    def test_bare_leder_og_admin_slipper_til(self):
        """André: «Den skal bare admin og leder ha tilgang til. For den
        genererer grunnlaget på alt.»"""
        for navn, c in (('les uten badge', self.c_leser),
                        ('korpsfører', self.c_kb),
                        ('skriv_full', self.c_vl)):
            with self.subTest(konto=navn):
                self.assertEqual(403, self._kall(c).status_code)
        self.assertEqual(0, Ressurs.objects.filter(vaktliste=self.vl2).count())

        for navn, c in (('skriv_leder', self.c_leder), ('admin', self.c_adm)):
            with self.subTest(konto=navn):
                res = self._kall(c, forhaandsvis=True)
                self.assertEqual(200, res.status_code)

    def test_genererer_og_svarer_med_tallene(self):
        res = self._kall(self.c_leder)
        self.assertEqual(200, res.status_code)
        data = res.json()['data']
        self.assertEqual(1, data['ressurser'])
        self.assertEqual(2, data['plasser'])
        self.assertEqual(16.0, data['timer'])
        self.assertEqual(2, Vaktpost.objects.filter(
            ressurs__vaktliste=self.vl2).count())

    def test_forhaandsvisning_skriver_ingenting(self):
        res = self._kall(self.c_leder, forhaandsvis=True)
        self.assertEqual(200, res.status_code)
        self.assertEqual(2, res.json()['data']['plasser'])
        self.assertEqual(0, Ressurs.objects.filter(vaktliste=self.vl2).count())

    def test_soepel_gir_400_med_melding_ikke_500(self):
        for navn, kropp in (
            ('ingen linjer', {'linjer': 'nei'}),
            ('linje som ikke er et objekt', {'linjer': ['nei']}),
            ('ingen vinduer', {'linjer': [{'gruppe_id': gruppe('Lag').pk,
                                           'vinduer': []}]}),
            ('vindu uten tid', {'linjer': [{'gruppe_id': gruppe('Lag').pk,
                                            'vinduer': [{'fra': '', 'til': ''}]}]}),
            ('ulesbart antall plasser', {'linjer': [{
                'gruppe_id': gruppe('Lag').pk,
                'vinduer': [{'fra': kl(2, 14).isoformat(),
                             'til': kl(2, 22).isoformat(),
                             'plasser': 'fire'}]}]}),
            ('null plasser', {'linjer': [{
                'gruppe_id': gruppe('Lag').pk,
                'vinduer': [{'fra': kl(2, 14).isoformat(),
                             'til': kl(2, 22).isoformat(),
                             'plasser': 0}]}]}),
        ):
            with self.subTest(tilfelle=navn):
                res = self._kall(self.c_leder, **kropp)
                self.assertEqual(400, res.status_code)
                self.assertTrue(res.json()['message'])

    def test_ukjent_vaktliste_gir_404(self):
        res = self.c_leder.post(
            '/vaktliste/api/vaktlister/999999/generer/',
            data=json.dumps({'linjer': []}),
            content_type='application/json')
        self.assertEqual(404, res.status_code)

    def test_get_avvises(self):
        res = self.c_leder.get(
            f'/vaktliste/api/vaktlister/{self.vl2.pk}/generer/')
        self.assertEqual(405, res.status_code)
