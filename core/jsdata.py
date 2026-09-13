"""Data inn i `<script>` — trygt (13. sep. 2026, sikkerhetsgjennomgangen H1).

`json.dumps` escaper ikke `<`, `>` og `&`. Settes resultatet inn i et
`<script>`-element med `|safe`, lukker et navn som inneholder `</script>`
skriptet og starter et nytt — og CSP-noncen hjelper ikke når vertslista
også står i `script-src`. Problemstillinger og enhetstyper heter det
`skriv_leder` skriver, så navnet er brukerdata.

`js_json()` gjør det Djangos `json_script` gjør: bytter de tre tegnene med
`\\u003c`, `\\u003e` og `\\u0026`, som JavaScript leser som de samme tegnene og
HTML-parseren ikke leser i det hele tatt. Returnerer `SafeString`, så malen
trenger ikke `|safe` — og skulle noen legge `|safe` på likevel, er verdien
alt trygg.
"""
import json

from django.utils.safestring import mark_safe

_ESCAPES = {ord('<'): '\\u003c', ord('>'): '\\u003e', ord('&'): '\\u0026'}


def js_json(verdi) -> str:
    """JSON for et `<script>`-element. Aldri `json.dumps` + `|safe` direkte."""
    return mark_safe(json.dumps(verdi).translate(_ESCAPES))
