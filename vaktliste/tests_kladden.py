"""Planleggerens kladd er bare for dem som kan skrive (26. sep. 2026, C2).

**André: «skjul, bare de som har skriverett kan se den».** En ledig plass som
ikke er delt ut — ikke reservert et korps, ikke åpnet for alle — er lederens
kladd. Tre kommentarer og grensesnittet lovet at den var «usynlig for korpsene
til du deler dem ut», men `synlige_vaktposter()` slapp alt gjennom for den som
ser alle korps: `les_alle` og `skriv_handling` så halvferdig planlegging som
om det var vaktlista. Bare `er_planlagt()` var prøvd, ikke synligheten.

**Kladd er en *ledig* plass.** En bemannet plass på en ressurs uten
reservasjon (KO) er ikke kladd — noen står der — og skal vises for alle som
ser alle korps. Derfor holder ikke `er_planlagt()` alene: den spør ikke om
personen.
"""
from __future__ import annotations

from datetime import timedelta

from accounts.models import ModulTilgang

from .models import Vaktpost
from .tests_tilgang import TilgangsBasis, _bruker, _klient


class KladdenErSkjultTests(TilgangsBasis):

    def setUp(self):
        super().setUp()
        til = self.na + timedelta(hours=8)
        felles = dict(ressurs=self.res_fri, fra_tid=self.na, til_tid=til)
        self.kladd = Vaktpost.objects.create(**felles)
        self.aapen = Vaktpost.objects.create(**felles, alle_korps=True)
        self.reservert = Vaktpost.objects.create(**felles, korps=self.karmoy)
        self.bemannet = Vaktpost.objects.create(**felles, mannskap=self.p_karmoy)
        self.paa_reservert_ressurs = Vaktpost.objects.create(
            ressurs=self.res_hgsd, fra_tid=self.na, til_tid=til)
        self.les_alle = _klient(_bruker('les_alle_c2', 'les_alle'))

    def _ser(self, klient):
        data = klient.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/').json()['data']
        return {vp['id'] for vp in data['vaktposter']}

    def test_under_skriv_full_ser_ingen_kladden(self):
        for navn, klient in (('les_alle', self.les_alle), ('skriv_handling', self.c_kb)):
            with self.subTest(konto=navn):
                ser = self._ser(klient)
                self.assertNotIn(self.kladd.pk, ser)
                self.assertTrue({self.aapen.pk, self.reservert.pk, self.bemannet.pk,
                                 self.paa_reservert_ressurs.pk} <= ser,
                                'alt som er delt ut eller bemannet, står')

    def test_skriveretten_ser_kladden(self):
        for navn, klient in (('skriv_full', self.c_vl), ('skriv_leder', self.c_leder),
                             ('global admin', self.c_adm)):
            with self.subTest(konto=navn):
                self.assertIn(self.kladd.pk, self._ser(klient))

    def test_en_ren_les_ser_den_heller_ikke(self):
        """Uendret: korpsfilteret tok den fra før."""
        leser = _bruker('leser_c2', 'les')
        from .models import Mannskap
        Mannskap.objects.create(navn='Leser', korps=self.hgsd, user=leser)
        self.assertNotIn(self.kladd.pk, self._ser(_klient(leser)))

    def test_timeoversikten_teller_ikke_kladden_for_les_alle(self):
        """Belastningen leser samme filter — ellers sto kladden der som ledige
        plasser for en som ikke skal se dem."""
        url = f'/vaktliste/api/vaktlister/{self.vl.pk}/belastning/'
        ledige = {navn: k.get(url).json()['data']['sammendrag']['ledige_plasser']
                  for navn, k in (('les_alle', self.les_alle), ('skriv_full', self.c_vl))}
        self.assertEqual(ledige, {'les_alle': 3, 'skriv_full': 4})
