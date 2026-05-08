"""Core-app: felles primitiver for sanitetsportalen.

Inneholder gjenbrukbare modeller, validatorer og decorators som flere apps
trenger. Andre apps (patients, accounts, vakter, oppdragsregistrering osv.)
kan importere herfra uten å skape sirkulære avhengigheter.

Avhengighetsgrafen:
    accounts ← core ← patients
                      ← oppdragsregistrering (fremtidig)
                      ← vakter (fremtidig)
                      ← utstyr (fremtidig)
                      ← rapport (fremtidig)
"""
