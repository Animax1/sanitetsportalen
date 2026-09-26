"""En peker til noe som ikke finnes, gir 400 med riktig navn (26. sep. 2026, A7).

**Tre feil med samme rot.** Fremmednøklene er utsatt til commit, så en
`korps_id`, `rolle_id` eller `enhet_id` som ikke finnes, ble først en
`IntegrityError` da `transaction.atomic()` lukket seg — og der sto en
`except` skrevet for noe helt annet:

- `vaktposter_view` formaterte `mannskap.navn` for en **ledig plass**, der
  `mannskap` er `None`. `AttributeError` i en `except` → **500**.
- `ressurser_view` og `ressurs_detalj_view` svarte «finnes allerede på denne
  vaktlista» om en ukjent enhet.
- `vaktpost_detalj_view` svarte «Personen står allerede …» om en ukjent rolle.

Pekerne slås nå opp før skrivingen (`_ukjent_peker`). Det kan skje: et
nedtrekk som ble tegnet før noen slettet rollen, sender en ID som var gyldig
da.

**Hvorfor testene ikke ser 500 direkte:** i en `TestCase` er
`transaction.atomic()` et savepoint, og de utsatte nøklene sjekkes først ved
commit, som aldri kommer. Uten rettingen blir raden laget med en peker ut i
løse lufta, og testen er rød fordi svaret er 201/200 og ikke 400.
"""
from __future__ import annotations

from .models import Ressurs, Vaktpost
from .tests_tilgang import TilgangsBasis

UKJENT = 987654


class UkjentePekereTests(TilgangsBasis):

    def _ny_plass(self, **kropp):
        kropp = {'fra_tid': self._iso(0), 'til_tid': self._iso(8), **kropp}
        return self.c_adm.post(f'/vaktliste/api/ressurser/{self.res_fri.pk}/vaktposter/',
                               data=kropp, content_type='application/json')

    def _feilmelding(self, res):
        self.assertEqual(res.status_code, 400, res.content)
        return res.json()['message']

    def test_ledig_plass_med_ukjent_rolle(self):
        self.assertEqual(self._feilmelding(self._ny_plass(rolle_id=UKJENT)), 'Ukjent rolle.')
        self.assertFalse(Vaktpost.objects.exists())

    def test_ledig_plass_med_ukjent_korps(self):
        self.assertEqual(self._feilmelding(self._ny_plass(korps_id=UKJENT)), 'Ukjent korps.')

    def test_ny_ressurs_med_ukjent_enhet(self):
        res = self.c_adm.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/ressurser/',
                              data={'navn': 'Ambulanse 9', 'gruppe_id': self.res_hgsd.gruppe_id,
                                    'enhet_id': UKJENT},
                              content_type='application/json')
        self.assertEqual(self._feilmelding(res), 'Ukjent enhet.')
        self.assertFalse(Ressurs.objects.filter(navn='Ambulanse 9').exists())

    def test_ressurs_endret_til_ukjent_korps(self):
        res = self.c_adm.put(f'/vaktliste/api/ressurser/{self.res_fri.pk}/',
                             data={'korps_id': UKJENT}, content_type='application/json')
        self.assertEqual(self._feilmelding(res), 'Ukjent korps.')
        self.res_fri.refresh_from_db()
        self.assertIsNone(self.res_fri.korps_id)

    def test_plass_endret_til_ukjent_rolle(self):
        plass = Vaktpost.objects.create(
            ressurs=self.res_fri, fra_tid=self.na, til_tid=self.na.replace(year=self.na.year + 1))
        res = self.c_adm.put(f'/vaktliste/api/vaktposter/{plass.pk}/',
                             data={'rolle_id': UKJENT}, content_type='application/json')
        self.assertEqual(self._feilmelding(res), 'Ukjent rolle.')

    def test_tom_verdi_er_fortsatt_lov(self):
        """«Ingen valgt» sender `''`, og det betyr ingen peker — ikke en ukjent."""
        self.assertEqual(self._ny_plass(rolle_id='', korps_id='').status_code, 201)
