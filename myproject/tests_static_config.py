"""Tester for statisk-fil-konfigurasjonen.

Bakgrunn: `STATICFILES_STORAGE` ble fjernet i Django 5.1. Prosjektet kjører
5.2, så innstillingen sto igjen som død konfigurasjon og ble ignorert uten et
eneste varsel — hverken sjekk, advarsel eller feilmelding. Django falt tilbake
til `StaticFilesStorage`, som verken hasher filnavn eller lager manifest.

Konsekvensen var ikke synlig på serveren, som er det som gjorde den vond å
finne: filene lå riktig i containeren, og `curl` mot `/static/css/portal.css`
ga det nye innholdet. Men uten hashing serverte WhiteNoise fila under samme
navn med `max-age=14400`, så en bruker som hadde besøkt siden fikk den gamle
utgaven i inntil fire timer etter deploy.

Testene under sjekker **oppførsel, ikke innstillingsnavn**. En test på
`settings.STORAGES['staticfiles']['BACKEND']` ville gått god for nøyaktig den
samme feilen neste gang Django flytter en innstilling: navnet ville stått der,
og ingenting ville brukt det.
"""
from django.contrib.staticfiles.storage import ManifestFilesMixin, staticfiles_storage
from django.test import TestCase


class StatiskLagringTests(TestCase):

    def test_staticfiles_storage_hasher_filnavn(self):
        """Lagringen som faktisk er i bruk må lage hashede navn.

        Uten dette finnes ingen cache-busting, og en frontend-endring når
        ikke brukeren før nettleserens cache utløper av seg selv.
        """
        self.assertIsInstance(
            staticfiles_storage, ManifestFilesMixin,
            'Aktiv staticfiles-lagring hasher ikke filnavn. Sjekk at '
            'STORAGES["staticfiles"] er satt — STATICFILES_STORAGE ble '
            'fjernet i Django 5.1 og ignoreres i stillhet.',
        )

    def test_url_faar_hash_naar_manifestet_finnes(self):
        """Selve beviset: `{% static %}` skal gi et navn som endres med innholdet.

        Hoppes over hvis manifestet ikke er bygget lokalt — det lages av
        `collectstatic`, som kjører i release-fasen på Railway, ikke ved
        testkjøring.
        """
        try:
            url = staticfiles_storage.url('css/portal.css')
        except ValueError:
            self.skipTest('staticfiles.json mangler — kjør collectstatic')

        self.assertNotEqual(
            url, '/static/css/portal.css',
            'URL-en er uhashet, så nettleseren kan ikke se at fila er endret',
        )
        self.assertRegex(url, r'/static/css/portal\.[0-9a-f]{8,}\.css')
