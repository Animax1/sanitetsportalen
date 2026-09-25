# -*- coding: utf-8 -*-
"""Overnatting i vaktlista — hvem sover hvor (25. sep. 2026).

André: «Dens funksjon er for brannsikkerhet.» Svarene: per natt, bare
mannskap fra registeret, lederen setter opp rommene, `skriv_full` plasserer
alle og korps-føreren sitt eget korps, og alle med `les` ser hele lista.
"""
from datetime import date

from audit.models import AuditLog

from . import fil, overnatting, services
from .models import Mannskap, Overnatting, Overnattingsrom, Vaktpost
from .tests_planlegger import kl
from .tests_tilgang import TilgangsBasis, _bruker, _klient

FRE = date(2026, 10, 2)     # natt til lørdag 3. okt.
LOR = date(2026, 10, 3)     # natt til søndag
SON = date(2026, 10, 4)


class _Overnatting(TilgangsBasis):
    """Vakta går fre. 2. okt. 18:00 – søn. 4. okt. 16:00: to netter."""

    def setUp(self):
        super().setUp()
        self.vl.vakt.startet = kl(2, 18)
        self.vl.vakt.save(update_fields=['startet'])
        self.vl.planlagt_slutt = kl(4, 16)
        self.vl.save(update_fields=['planlagt_slutt'])
        self.rom = overnatting.lagre_rom(self.vl, {'navn': 'Klasserom 2B', 'kapasitet': 6})
        self.gym = overnatting.lagre_rom(self.vl, {'navn': 'Gymsal'})

    def _plasser(self, klient, rom, mannskap, netter, **ekstra):
        return klient.post(f'/vaktliste/api/overnattingsrom/{rom.pk}/plasser/',
                           data={'mannskap_id': mannskap.pk, 'netter': netter, **ekstra},
                           content_type='application/json')


class NetteneTests(_Overnatting):

    def test_nettene_er_de_vakta_gaar_over(self):
        self.assertEqual(overnatting.netter_i_vakta(self.vl), [FRE, LOR])

    def test_en_dagvakt_har_ingen_netter(self):
        self.vl.vakt.startet = kl(3, 8)
        self.vl.planlagt_slutt = kl(3, 20)
        self.assertEqual(overnatting.netter_i_vakta(self.vl), [])

    def test_natta_teller_naar_vakta_bare_rører_den(self):
        """Slutt 22:30 lørdag er en halvtime inn i lørdagsnatta — folk sover
        der. Slutt nøyaktig 22:00 er det ikke."""
        self.vl.planlagt_slutt = kl(3, 22, 30)
        self.assertEqual(overnatting.netter_i_vakta(self.vl), [FRE, LOR])
        self.vl.planlagt_slutt = kl(3, 22)
        self.assertEqual(overnatting.netter_i_vakta(self.vl), [FRE])

    def test_start_etter_midnatt_er_natta_som_begynte_kvelden_foer(self):
        """Lokal tid, ikke UTC: 02:00 norsk tid er natta fra fredag."""
        self.vl.vakt.startet = kl(3, 2)
        self.vl.planlagt_slutt = kl(3, 5)
        self.assertEqual(overnatting.netter_i_vakta(self.vl), [FRE])
        self.vl.planlagt_slutt = None
        self.assertEqual(overnatting.netter_i_vakta(self.vl), [FRE])

    def test_uten_slutt_er_det_bare_natta_vakta_begynner(self):
        self.vl.planlagt_slutt = None
        self.assertEqual(overnatting.netter_i_vakta(self.vl), [FRE])

    def test_uten_start_ingen_netter(self):
        self.vl.vakt.startet = None
        self.assertEqual(overnatting.netter_i_vakta(self.vl), [])

    def test_et_urimelig_spenn_kappes(self):
        self.vl.planlagt_slutt = kl(2, 18).replace(year=2027)
        self.assertEqual(len(overnatting.netter_i_vakta(self.vl)), overnatting.MAKS_NETTER)

    def test_en_brukt_natt_forsvinner_ikke_naar_vakta_kortes(self):
        overnatting.plasser(self.rom, self.p_hgsd, [LOR.isoformat()])
        self.vl.planlagt_slutt = kl(3, 12)
        self.vl.save(update_fields=['planlagt_slutt'])
        self.assertEqual(overnatting.netter_i_vakta(self.vl), [FRE])
        self.assertEqual(overnatting.netter(self.vl), [FRE, LOR])

    def test_natt_tekst_bruker_morgenens_dag(self):
        self.assertEqual(overnatting.natt_tekst(FRE), 'Natt til lørdag 03.10')


class RommeneTests(_Overnatting):

    def test_navnet_er_unikt_per_liste_uansett_store_bokstaver(self):
        with self.assertRaisesRegex(overnatting.Ugyldig, 'alt et rom'):
            overnatting.lagre_rom(self.vl, {'navn': 'klasserom 2b'})
        annen = services.opprett_planlagt_vakt('Neste vakt')
        overnatting.lagre_rom(annen, {'navn': 'Klasserom 2B'})

    def test_navn_kreves_og_kapasiteten_valideres(self):
        with self.assertRaisesRegex(overnatting.Ugyldig, 'navn'):
            overnatting.lagre_rom(self.vl, {'navn': '  '})
        for feil in ('tre', 0, -1, 501):
            with self.subTest(kapasitet=feil), self.assertRaises(overnatting.Ugyldig):
                overnatting.lagre_rom(self.vl, {'navn': f'R{feil}', 'kapasitet': feil})
        rom = overnatting.lagre_rom(self.vl, {'navn': 'Tomt tak', 'kapasitet': ''})
        self.assertIsNone(rom.kapasitet)

    def test_nye_rom_legges_sist(self):
        self.assertLess(self.rom.rekkefolge, self.gym.rekkefolge)

    def test_endring_roerer_bare_feltene_som_sendes(self):
        overnatting.lagre_rom(self.vl, {'plassering': 'Skolen, 2. etg'}, rom=self.rom)
        self.rom.refresh_from_db()
        self.assertEqual((self.rom.navn, self.rom.kapasitet, self.rom.plassering),
                         ('Klasserom 2B', 6, 'Skolen, 2. etg'))


class PlasseringTests(_Overnatting):

    def test_en_person_sover_ett_sted_per_natt(self):
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        with self.assertRaises(overnatting.Konflikt) as k:
            overnatting.plasser(self.gym, self.p_hgsd, [FRE.isoformat(), LOR.isoformat()])
        self.assertEqual(k.exception.netter, [FRE.isoformat()])
        self.assertIn('Klasserom 2B', str(k.exception))
        # Ingenting ble skrevet — heller ikke lørdagen som var ledig.
        self.assertEqual(Overnatting.objects.filter(mannskap=self.p_hgsd).count(), 1)

    def test_flytt_flytter(self):
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        overnatting.plasser(self.gym, self.p_hgsd, [FRE.isoformat(), LOR.isoformat()],
                            flytt=True)
        rader = Overnatting.objects.filter(mannskap=self.p_hgsd)
        self.assertEqual({(o.rom_id, o.natt) for o in rader},
                         {(self.gym.pk, FRE), (self.gym.pk, LOR)})

    def test_samme_rom_igjen_er_ingen_endring(self):
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        self.assertEqual(Overnatting.objects.count(), 1)

    def test_en_seng_paa_en_annen_vakt_flyttes_aldri_herfra(self):
        annen = services.opprett_planlagt_vakt('Nabovakta')
        annen.vakt.startet = kl(2, 18)
        annen.vakt.save(update_fields=['startet'])
        annen.planlagt_slutt = kl(3, 12)
        annen.save(update_fields=['planlagt_slutt'])
        der = overnatting.lagre_rom(annen, {'navn': 'Hall'})
        overnatting.plasser(der, self.p_hgsd, [FRE.isoformat()])
        with self.assertRaisesRegex(overnatting.Ugyldig, 'annen vakt'):
            overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()], flytt=True)
        self.assertEqual(Overnatting.objects.get(mannskap=self.p_hgsd).rom, der)

    def test_en_kollisjon_midt_i_skrivingen_etterlater_ingenting(self):
        """Noen plasserer henne lørdag i samme øyeblikk som vi skriver fredag
        og lørdag. Da skal fredagen heller ikke stå — en halv plassering er en
        brannliste som sier noe ingen har bestemt."""
        from unittest import mock
        from django.db import IntegrityError
        ekte = Overnatting.objects.create
        kall = []

        def create(**kw):
            kall.append(kw['natt'])
            if len(kall) == 2:
                raise IntegrityError('duplicate key')
            return ekte(**kw)

        with mock.patch.object(Overnatting.objects, 'create', side_effect=create):
            with self.assertRaisesRegex(overnatting.Ugyldig, 'nettopp plassert'):
                overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat(), LOR.isoformat()])
        self.assertEqual(kall, [FRE, LOR])
        self.assertFalse(Overnatting.objects.exists())

    def test_bare_vaktas_netter(self):
        with self.assertRaisesRegex(overnatting.Ugyldig, 'går ikke over natta'):
            overnatting.plasser(self.rom, self.p_hgsd, [SON.isoformat()])
        for feil in ([], None, 'fredag', ['i morgen']):
            with self.subTest(netter=feil), self.assertRaises(overnatting.Ugyldig):
                overnatting.plasser(self.rom, self.p_hgsd, feil)

    def test_pensjonert_mannskap_plasseres_ikke(self):
        self.p_hgsd.er_aktiv = False
        self.p_hgsd.save()
        with self.assertRaisesRegex(overnatting.Ugyldig, 'ikke aktiv'):
            overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])

    def test_rommet_tar_plasseringene_med_seg(self):
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat(), LOR.isoformat()])
        self.assertEqual(overnatting.slett_rom(self.rom), 2)
        self.assertFalse(Overnatting.objects.exists())

    def test_personen_kan_ikke_slettes_fra_registeret_mens_hun_staar_paa_lista(self):
        from django.db.models.deletion import ProtectedError
        overnatting.plasser(self.rom, self.p_karmoy, [FRE.isoformat()])
        with self.assertRaises(ProtectedError):
            self.p_karmoy.delete()


class PaaVaktINattTests(_Overnatting):
    """Den som kjører 22–06 er ikke i rommet — lista skal si det."""

    def _skift(self, fra, til, **kw):
        return Vaktpost.objects.create(ressurs=self.res_hgsd, mannskap=self.p_hgsd,
                                       fra_tid=fra, til_tid=til, **kw)

    def _vakt(self):
        rader = list(Overnatting.objects.select_related('mannskap'))
        return overnatting.paa_vakt(self.vl, rader)

    def test_nattskift_er_paa_vakt_dagskift_er_ikke(self):
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat(), LOR.isoformat()])
        natt = self._skift(kl(2, 22), kl(3, 6))
        self._skift(kl(3, 8), kl(3, 16))
        vakt = self._vakt()
        self.assertEqual(vakt[(self.p_hgsd.pk, FRE)], [natt])
        self.assertNotIn((self.p_hgsd.pk, LOR), vakt)

    def test_kanten_teller_ikke(self):
        """Skift som slutter 22:00 eller begynner 06:00 er utenfor natta."""
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        self._skift(kl(2, 14), kl(2, 22))
        self._skift(kl(3, 6), kl(3, 14))
        self.assertEqual(self._vakt(), {})
        del_av = self._skift(kl(3, 5), kl(3, 7))
        self.assertEqual(self._vakt()[(self.p_hgsd.pk, FRE)], [del_av])

    def test_kanten_teller_ikke_heller_naar_nettene_er_flere(self):
        """Med to netter henter spørringen hele spennet, og da er det løkka
        alene som holder lørdagens dagskift 06–14 utenfor fredagsnatta."""
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat(), LOR.isoformat()])
        self._skift(kl(3, 6), kl(3, 14))
        self._skift(kl(3, 14), kl(3, 22))
        self.assertEqual(self._vakt(), {})

    def test_avmeldt_skift_teller_ikke(self):
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        self._skift(kl(2, 22), kl(3, 6), avmeldt_at=kl(2, 12))
        self.assertEqual(self._vakt(), {})

    def test_skift_paa_en_annen_vakt_teller_ikke(self):
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        annen = services.opprett_planlagt_vakt('Nabovakta')
        from .test_helpers import lag_ressurs
        r = lag_ressurs(vaktliste=annen, navn='Der')
        Vaktpost.objects.create(ressurs=r, mannskap=self.p_hgsd,
                                fra_tid=kl(2, 22), til_tid=kl(3, 6))
        self.assertEqual(self._vakt(), {})


class EndepunktTilgangTests(_Overnatting):
    """Tre terskler: rommene er lederens, plasseringen følger personens korps,
    og lista ses av alle med `les`."""

    def test_rom_opprettes_bare_av_lederen(self):
        url = f'/vaktliste/api/vaktlister/{self.vl.pk}/overnattingsrom/'
        for navn, c in (('les', self.c_leser), ('skriv_handling', self.c_kb),
                        ('skriv_full', self.c_vl)):
            with self.subTest(konto=navn):
                res = c.post(url, data={'navn': f'Rom {navn}'},
                             content_type='application/json')
                self.assertEqual(res.status_code, 403)
        for navn, c in (('skriv_leder', self.c_leder), ('admin', self.c_adm)):
            with self.subTest(konto=navn):
                res = c.post(url, data={'navn': f'Rom {navn}', 'kapasitet': 4},
                             content_type='application/json')
                self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(Overnattingsrom.objects.filter(navn__startswith='Rom ').count(), 2)

    def test_rom_endres_og_slettes_bare_av_lederen_og_sletting_krever_bekreftelse(self):
        url = f'/vaktliste/api/overnattingsrom/{self.rom.pk}/'
        res = self.c_vl.put(url, data={'navn': 'Nytt'}, content_type='application/json')
        self.assertEqual(res.status_code, 403)
        res = self.c_leder.put(url, data={'navn': 'Nytt'}, content_type='application/json')
        self.assertEqual(res.json()['data']['navn'], 'Nytt')
        res = self.c_vl.delete(url, data={'confirm': True}, content_type='application/json')
        self.assertEqual(res.status_code, 403)
        res = self.c_leder.delete(url, content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertTrue(Overnattingsrom.objects.filter(pk=self.rom.pk).exists())
        res = self.c_leder.delete(url, data={'confirm': True}, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Overnattingsrom.objects.filter(pk=self.rom.pk).exists())

    def test_korpsfoereren_plasserer_bare_sitt_eget_korps(self):
        natt = [FRE.isoformat()]
        self.assertEqual(self._plasser(self.c_kb, self.rom, self.p_karmoy, natt).status_code, 403)
        self.assertEqual(self._plasser(self.c_kb, self.rom, self.p_hgsd, natt).status_code, 201)
        self.assertEqual(self._plasser(self.c_leser, self.rom, self.p_hgsd,
                                       [LOR.isoformat()]).status_code, 403)
        self.assertEqual(self._plasser(self.c_vl, self.rom, self.p_karmoy, natt).status_code, 201)

    def test_fjerning_foelger_samme_regel(self):
        overnatting.plasser(self.rom, self.p_karmoy, [FRE.isoformat()])
        rad = Overnatting.objects.get()
        url = f'/vaktliste/api/overnattinger/{rad.pk}/'
        self.assertEqual(self.c_kb.delete(url).status_code, 403)
        self.assertEqual(self.c_leser.delete(url).status_code, 403)
        self.assertEqual(self.c_vl.delete(url).status_code, 200)
        self.assertFalse(Overnatting.objects.exists())

    def test_konflikt_gir_409_med_nettene_og_flytt_flytter(self):
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        res = self._plasser(self.c_vl, self.gym, self.p_hgsd, [FRE.isoformat()])
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()['konflikt'], [FRE.isoformat()])
        res = self._plasser(self.c_vl, self.gym, self.p_hgsd, [FRE.isoformat()], flytt=True)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Overnatting.objects.get().rom, self.gym)

    def test_flytt_maa_vaere_sant_ikke_bare_sannaktig(self):
        """`"flytt": "false"` er en streng og sann i Python; bare `true` flytter."""
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        res = self._plasser(self.c_vl, self.gym, self.p_hgsd, [FRE.isoformat()], flytt='false')
        self.assertEqual(res.status_code, 409)

    def test_ukjent_person_og_rom(self):
        res = self.c_vl.post(f'/vaktliste/api/overnattingsrom/{self.rom.pk}/plasser/',
                             data={'mannskap_id': 'x', 'netter': [FRE.isoformat()]},
                             content_type='application/json')
        self.assertEqual(res.status_code, 400)
        res = self._plasser(self.c_vl, Overnattingsrom(pk=9999), self.p_hgsd, [FRE.isoformat()])
        self.assertEqual(res.status_code, 404)

    def test_brannrutinen_er_lederens(self):
        url = f'/vaktliste/api/vaktlister/{self.vl.pk}/'
        tekst = 'Samleplass: parkeringsplassen nord.'
        res = self.c_vl.put(url, data={'brannrutine': tekst}, content_type='application/json')
        self.assertEqual(res.status_code, 403)
        res = self.c_leder.put(url, data={'brannrutine': tekst}, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.vl.refresh_from_db()
        self.assertEqual(self.vl.brannrutine, tekst)
        # Ingen andre felter ble rørt av en PUT med bare rutinen.
        self.assertEqual(self.vl.planlagt_slutt, kl(4, 16))
        res = self.c_leder.put(url, data={'brannrutine': 'x' * 2001},
                               content_type='application/json')
        self.assertEqual(res.status_code, 400)


class LesingenTests(_Overnatting):
    """Alle med `les` ser hele lista — telefonen følger korpsfilteret."""

    def setUp(self):
        super().setUp()
        self.p_hgsd.telefon = '900 00 000'
        self.p_hgsd.save()
        self.p_karmoy.telefon = '911 11 111'
        self.p_karmoy.save()
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        overnatting.plasser(self.rom, self.p_karmoy, [FRE.isoformat()])

    def _data(self, klient):
        res = klient.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/')
        self.assertEqual(res.status_code, 200)
        return res.json()['data']['overnatting']

    def test_leseren_ser_alle_navn_men_bare_eget_korps_telefon(self):
        leser = _bruker('leser_hgsd', 'les')
        Mannskap.objects.create(navn='Leser', korps=self.hgsd, user=leser)
        data = self._data(_klient(leser))
        self.assertEqual(sorted(p['navn'] for p in data['plasseringer']), ['Kari', 'Ola'])
        telefon = {p['navn']: p['telefon'] for p in data['plasseringer']}
        self.assertEqual(telefon, {'Kari': '900 00 000', 'Ola': ''})

    def test_leser_uten_badge_ser_navnene_uten_telefon(self):
        data = self._data(self.c_leser)
        self.assertEqual(len(data['plasseringer']), 2)
        self.assertEqual({p['telefon'] for p in data['plasseringer']}, {''})

    def test_den_som_ser_alle_ser_alle_telefoner(self):
        data = self._data(self.c_kb)
        self.assertEqual({p['telefon'] for p in data['plasseringer']},
                         {'900 00 000', '911 11 111'})

    def test_svaret_baerer_nettene_rommene_og_rutinen(self):
        self.vl.brannrutine = 'Ring 110'
        self.vl.save(update_fields=['brannrutine'])
        data = self._data(self.c_vl)
        self.assertEqual(data['netter'], [FRE.isoformat(), LOR.isoformat()])
        self.assertEqual([r['navn'] for r in data['rom']], ['Klasserom 2B', 'Gymsal'])
        self.assertEqual(data['rom'][0]['kapasitet'], 6)
        self.assertEqual(data['brannrutine'], 'Ring 110')

    def test_paa_vakt_staar_i_svaret(self):
        Vaktpost.objects.create(ressurs=self.res_hgsd, mannskap=self.p_hgsd,
                                fra_tid=kl(2, 22), til_tid=kl(3, 6))
        data = self._data(self.c_vl)
        kari = next(p for p in data['plasseringer'] if p['navn'] == 'Kari')
        self.assertEqual([s['ressurs'] for s in kari['paa_vakt']], ['Lag HGSD'])


class FilaOgAuditTests(_Overnatting):

    def test_brannlista_staar_i_fila(self):
        self.p_hgsd.telefon = '900 00 000'
        self.p_hgsd.save()
        self.vl.brannrutine = 'Samleplass: <parkeringen>'
        self.vl.save(update_fields=['brannrutine'])
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        Vaktpost.objects.create(ressurs=self.res_hgsd, mannskap=self.p_hgsd,
                                fra_tid=kl(2, 22), til_tid=kl(3, 6))
        # Bare brannlistebolken: Kari står også i vaktlistedelen av fila, med
        # telefon, og en assertion mot hele fila traff den i stedet.
        html = fil.bygg_fil(self.vl).split('Brannliste – hvem sover hvor')[1]
        self.assertIn('Natt til lørdag 03.10', html)
        self.assertIn('Klasserom 2B', html)
        self.assertIn('900 00 000', html)
        self.assertIn('Lag HGSD 22:00–06:00', html)
        self.assertIn('0 skal være inne', html)
        self.assertIn('&lt;parkeringen&gt;', html)

    def test_hver_natt_i_fila_har_bare_sine_egne(self):
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        overnatting.plasser(self.rom, self.p_karmoy, [LOR.isoformat()])
        natt = {n['natt']: [p['navn'] for r in n['rom'] for p in r['folk']]
                for n in overnatting.brannliste(self.vl)}
        self.assertEqual(natt, {FRE.isoformat(): ['Kari'], LOR.isoformat(): ['Ola']})

    def test_uten_plasseringer_ingen_bolk_og_samme_signatur_som_foer(self):
        self.assertNotIn('Brannliste', fil.bygg_fil(self.vl))
        grupper = fil.rader_for(self.vl)
        self.assertEqual(fil.signatur(grupper, overnatting.brannliste(self.vl)),
                         fil.signatur(grupper))

    def test_en_plassering_endrer_signaturen(self):
        grupper = fil.rader_for(self.vl)
        foer = fil.signatur(grupper, overnatting.brannliste(self.vl))
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        self.assertNotEqual(fil.signatur(grupper, overnatting.brannliste(self.vl)), foer)

    def test_intervallsendingen_ser_en_ny_plassering(self):
        """Kallstedet, ikke bare hjelperen: `send_planlagte` må ta brannlista
        med i sammenligningen, ellers går en ny plassering aldri ut."""
        from datetime import timedelta
        from unittest import mock
        from core.models import AppSetting
        from django.utils import timezone
        from . import choices
        AppSetting.set(fil.MOTTAKERE_NOKKEL, 'a@example.no')
        AppSetting.set(fil.INTERVALL_NOKKEL, '10')
        self.vl.status = choices.DRIFT
        self.vl.save(update_fields=['status'])
        fil.send_fil(self.vl)
        senere = timezone.now() + timedelta(minutes=11)
        with mock.patch.object(fil, 'send_fil') as send:
            fil.send_planlagte(naa=senere)
            send.assert_not_called()
            overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
            fil.send_planlagte(naa=senere)
            send.assert_called_once()

    def test_plassering_og_rom_auditlogges(self):
        overnatting.plasser(self.rom, self.p_hgsd, [FRE.isoformat()])
        rad = AuditLog.objects.get(table_name='vaktliste_overnatting', action='CREATE')
        self.assertIn('Kari i Klasserom 2B', rad.new_value)
        overnatting.plasser(self.gym, self.p_hgsd, [FRE.isoformat()], flytt=True)
        self.assertTrue(AuditLog.objects.filter(
            table_name='vaktliste_overnatting', action='UPDATE', field_name='rom',
            old_value='Klasserom 2B', new_value='Gymsal').exists())
        overnatting.slett_rom(self.gym)
        self.assertTrue(AuditLog.objects.filter(
            table_name='vaktliste_overnatting', action='DELETE').exists())
        self.assertTrue(AuditLog.objects.filter(
            table_name='vaktliste_overnattingsrom', action='DELETE',
            old_value='Gymsal').exists())

    def test_brannrutinen_auditlogges_med_verdi(self):
        self.vl.brannrutine = 'Samleplass nord'
        self.vl.save()
        self.assertTrue(AuditLog.objects.filter(
            table_name='vaktliste_vaktliste', field_name='brannrutine',
            new_value='Samleplass nord').exists())


class LagringstidenTests(_Overnatting):
    """Plasseringene slettes 30 dager etter natta (André, 25. sep. 2026: «Gjør
    A»). **Prøvd gjennom `purge_old_logs`**, ikke gjennom hjelperen: registeret
    er koblingen, og en test som hopper over det ville ikke merket at den røk."""

    def _natt(self, dager_siden, mannskap=None, rom=None):
        from datetime import timedelta
        from django.utils import timezone
        natt = timezone.localtime().date() - timedelta(days=dager_siden)
        return Overnatting.objects.create(rom=rom or self.rom,
                                          mannskap=mannskap or self.p_hgsd, natt=natt)

    def _purge(self, *args):
        from io import StringIO
        from django.core.management import call_command
        ut = StringIO()
        call_command('purge_old_logs', *args, stdout=ut)
        return ut.getvalue()

    def test_registrert_med_fristen_modulen_bruker(self):
        from core.opprydding import all_handlers
        handler = next(h for h in all_handlers() if h.slug == 'vaktliste')
        self.assertEqual(handler.frist_dager(), overnatting.OPPBEVARING_DAGER)
        self.assertEqual(overnatting.OPPBEVARING_DAGER, 30)

    def test_eldre_enn_tretti_dager_slettes_rommene_staar(self):
        gammel = self._natt(31)
        grensen = self._natt(30, mannskap=self.p_karmoy)
        ut = self._purge()
        self.assertFalse(Overnatting.objects.filter(pk=gammel.pk).exists())
        self.assertTrue(Overnatting.objects.filter(pk=grensen.pk).exists())
        self.assertTrue(Overnattingsrom.objects.filter(pk=self.rom.pk).exists())
        self.assertIn('Slettet 1 overnattingsplasseringer', ut)

    def test_toerrkjoering_sletter_ingenting(self):
        self._natt(40)
        ut = self._purge('--dry-run')
        self.assertEqual(Overnatting.objects.count(), 1)
        self.assertIn('Ville slettet 1 overnattingsplasseringer', ut)

    def test_ryddingen_skriver_ikke_navnene_inn_i_auditloggen(self):
        """Slettesignalet logger navn, rom og natt. Fyrte det under ryddingen,
        ville det bevart i 730 dager det som skulle bort etter 30."""
        self._natt(31)
        AuditLog.objects.all().delete()
        self._purge()
        self.assertFalse(AuditLog.objects.filter(
            table_name='vaktliste_overnatting').exists())

    def test_en_vanlig_fjerning_logges_fortsatt(self):
        """Flagget skal bare gjelde ryddingen — og slippes etterpå."""
        self._natt(31)
        self._purge()
        rad = self._natt(1)
        overnatting.fjern(rad)
        self.assertTrue(AuditLog.objects.filter(
            table_name='vaktliste_overnatting', action='DELETE').exists())

    def test_fristen_regnes_i_norsk_dato(self):
        """23:30 UTC 31. okt. er 00:30 1. nov. i Norge (vintertid). Natta fra
        1. okt. er da 31 dager gammel og skal ut; med `.date()` rett på
        UTC-tidspunktet ville den stått én dag til."""
        from datetime import datetime, timezone as dt_timezone
        Overnatting.objects.create(rom=self.rom, mannskap=self.p_hgsd, natt=date(2026, 10, 1))
        naa = datetime(2026, 10, 31, 23, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(overnatting.utlopte(naa).count(), 1)
