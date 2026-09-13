"""Sikkerhetssjekk av en kjørende portal, utenfra — kjøres mot staging.

    python scripts/sikkerhetssjekk.py https://testportal.sanitet.net
    python scripts/sikkerhetssjekk.py https://testportal.sanitet.net --admin admin --leser kari --enhet bil1

Bare standardbiblioteket. Uten kontoer testes det som kan testes anonymt:
transport (HTTPS, HSTS, CSP og de andre hodene), cookieflagg, at ingen side
eller API svarer 200 uten innlogging, CSRF, rate-limiting på innlogging,
feilsider uten traceback, og at Django-admin og kjente filer ikke finnes.
Med kontoer testes i tillegg rollegrensene: leseren skal ikke nå admin-sidene
eller kunne skrive, enhetskontoen skal ikke nå sentralens oppsett, og admin
skal nå det. Passord og MFA-kode spørres det om interaktivt — ingenting
lagres.

Kjør den mot STAGING. Rate-limit-testen bruker et tilfeldig brukernavn som
ikke finnes, så ingen konto låses, men IP-bøtta (50 forsøk per 5 min) fylles
med 11 — kjør ikke scriptet fem ganger på rad fra samme nett. Utskriften er
rapporten: lim den inn i chatten.
"""
from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import random
import re
import string
import sys
import urllib.error
import urllib.parse
import urllib.request

# ── Det som skal være stengt uten innlogging ──────────────────────────────────
# Fra `urlpatterns` 13. sep. 2026. <pk> er byttet med 1 — 404 er også et
# godkjent svar, poenget er at svaret aldri er 200 (eller 500).
STENGT_GET = [
    '/', '/min-profil/', '/varsler/', '/api/varsler/', '/api/varsler/ulest-antall/',
    '/accounts/change-password/', '/portal-admin/brukere/', '/portal-admin/brukere/ny/',
    '/portal-admin/brukere/1/', '/portal-admin/innloggingslogg/', '/portal-admin/innstillinger/',
    '/portal-admin/moduler/', '/portal-admin/moduler/patients/', '/portal-admin/auditlog/',
    '/portal-admin/auditlog/eksport.csv', '/portal-admin/backup/', '/portal-admin/backup/patients/',
    '/portal-admin/backup/patients/last-ned/1/', '/portal-admin/server-status/',
    '/portal-admin/server-status/json/', '/portal-admin/server-status/sessions/',
    '/pasienter/', '/pasienter/api/settings/', '/pasienter/api/patients/', '/pasienter/api/patients/1/',
    '/pasienter/api/forstehjelpere/', '/pasienter/api/helsepersonell/', '/pasienter/api/vakter/',
    '/pasienter/api/innstillinger/arkiv/', '/pasienter/api/innstillinger/arkiv/1/',
    '/statistikk/', '/statistikk/api/kilde/patients/full-stats/', '/statistikk/api/kilde/oppdrag/full-stats/',
    '/statistikk/api/kilde/patients/arkiv/1/full-stats/',
    '/oppdrag/', '/oppdrag/api/enheter/', '/oppdrag/api/enheter/1/', '/oppdrag/api/lokasjoner/',
    '/oppdrag/api/enhetstyper/', '/oppdrag/api/problemstillinger/', '/oppdrag/api/bilinnstillinger/',
    '/oppdrag/api/oppdrag/', '/oppdrag/api/oppdrag/1/', '/oppdrag/api/historikk/', '/oppdrag/api/arkiv/',
    '/oppdrag/api/arkiv/1/', '/oppdrag/api/oppdrag/1/historikk/',
    '/vaktliste/', '/vaktliste/api/vaktlister/', '/vaktliste/api/vaktlister/1/',
    '/vaktliste/api/vaktlister/1/ressurser/', '/vaktliste/api/ressurser/1/', '/vaktliste/api/ressurser/1/vaktposter/',
    '/vaktliste/api/vaktposter/1/', '/vaktliste/api/enhet/1/besetning/', '/vaktliste/api/vaktlister/1/belastning/',
    '/vaktliste/api/grenser/', '/vaktliste/api/vaktlister/1/fil/', '/vaktliste/api/mannskap/',
    '/vaktliste/api/mannskap/1/', '/vaktliste/api/korps/', '/vaktliste/api/kompetanser/',
    '/vaktliste/api/grupper/', '/vaktliste/api/roller/',
]
# Skriveendepunkter: uten innlogging og uten CSRF-token skal svaret være 403
# (CSRF) eller en omdirigering — aldri 200, aldri 500.
STENGT_POST = [
    '/pasienter/api/patients/', '/pasienter/api/avslutt-vakt/', '/pasienter/api/innstillinger/arkiv/lagre/',
    '/oppdrag/api/oppdrag/', '/oppdrag/api/lokasjoner/', '/oppdrag/api/oppdrag/1/status/rykker_ut/',
    '/vaktliste/api/vaktlister/', '/vaktliste/api/mannskap/', '/vaktliste/api/vaktposter/1/stempling/mott/',
    '/vaktliste/api/vaktlister/1/drift/start/', '/vaktliste/api/vaktlister/1/fil/send/',
    '/portal-admin/backup/patients/run/', '/portal-admin/server-status/sessions/kill-all/',
    '/accounts/logout/',
]
# Skal svare uten innlogging — og bare disse.
AAPENT = ['/healthz/', '/robots.txt', '/manifest.webmanifest', '/accounts/login/',
          '/accounts/glemt-passord/', '/vaktliste/sw.js']
# Skal ikke finnes.
FINNES_IKKE = ['/django-admin/', '/admin/', '/.env', '/.git/config', '/static/', '/backups/',
               '/manage.py', '/myproject/settings.py', '/wp-login.php']

ADMIN_SIDER = ['/portal-admin/server-status/', '/portal-admin/brukere/', '/portal-admin/backup/',
               '/portal-admin/auditlog/', '/portal-admin/innstillinger/', '/portal-admin/moduler/',
               '/portal-admin/server-status/json/']


class Rapport:
    def __init__(self):
        self.linjer = []
        self.antall = {'OK': 0, 'FEIL': 0, 'INFO': 0, 'HOPP': 0}

    def _si(self, status, tekst):
        self.antall[status] += 1
        linje = f'[{status:4}] {tekst}'
        self.linjer.append(linje)
        print(linje, flush=True)

    def ok(self, t): self._si('OK', t)
    def feil(self, t): self._si('FEIL', t)
    def info(self, t): self._si('INFO', t)
    def hopp(self, t): self._si('HOPP', t)
    def sjekk(self, betingelse, tekst_ok, tekst_feil=None):
        (self.ok if betingelse else self.feil)(tekst_ok if betingelse else (tekst_feil or tekst_ok))

    def overskrift(self, t):
        linje = f'\n── {t} ──'
        self.linjer.append(linje)
        print(linje, flush=True)


class Klient:
    """Én cookiejar = én nettleser. Følger ikke omdirigeringer — vi vil se dem."""

    class _IngenRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    def __init__(self, base):
        self.base = base.rstrip('/')
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), self._IngenRedirect)

    def kall(self, sti, metode='GET', data=None, json_data=None, hoder=None, csrf=False, timeout=20):
        url = sti if sti.startswith('http') else self.base + sti
        kropp = None
        h = {'User-Agent': 'sikkerhetssjekk/1.0', 'Accept': 'text/html,application/json'}
        if json_data is not None:
            kropp = json.dumps(json_data).encode()
            h['Content-Type'] = 'application/json'
        elif data is not None:
            kropp = urllib.parse.urlencode(data).encode()
            h['Content-Type'] = 'application/x-www-form-urlencoded'
        if csrf:
            tok = self.cookie('csrftoken')
            if tok:
                h['X-CSRFToken'] = tok
            h['Referer'] = self.base + '/'
        h.update(hoder or {})
        req = urllib.request.Request(url, data=kropp, method=metode, headers=h)
        # Hodenavnene normaliseres til små bokstaver: Cloudflare og HTTP/2 sender
        # `location`, gunicorn direkte sender `Location` — første kjøring mot
        # staging meldte 64 falske FEIL på det.
        try:
            with self.opener.open(req, timeout=timeout) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode('utf-8', 'replace')

    def cookie(self, navn):
        for c in self.jar:
            if c.name == navn:
                return c.value
        return None

    def cookieobj(self, navn):
        for c in self.jar:
            if c.name == navn:
                return c
        return None

    def sett_cookie(self, navn, verdi):
        vert = urllib.parse.urlparse(self.base).hostname
        self.jar.set_cookie(http.cookiejar.Cookie(
            0, navn, verdi, None, False, vert, True, False, '/', True, True, None, False, None, None, {}))


def _skjemafelt(html, navn):
    m = re.search(r'name="' + re.escape(navn) + r'"[^>]*value="([^"]*)"', html)
    return m.group(1) if m else None


def logg_inn(k: Klient, r: Rapport, bruker, passord, rolle):
    """Innlogging med MFA-steg. Returnerer True når /min-profil/ svarer 200."""
    st, h, html = k.kall('/accounts/login/')
    tok = _skjemafelt(html, 'csrfmiddlewaretoken')
    sesjon_for = k.cookie('sessionid')
    st, h, html = k.kall('/accounts/login/', 'POST', data={
        'csrfmiddlewaretoken': tok or '', 'username': bruker, 'password': passord, 'next': '/'}, csrf=True)
    if st == 429:
        r.feil(f'{rolle}: innloggingen er rate-limitet (429) — vent 5 min og prøv igjen')
        return False
    st2, h2, html2 = k.kall('/accounts/login/')
    for _ in range(3):
        if 'totp_code' not in html2 and 'backup_code' not in html2:
            break
        kode = input(f'  MFA-kode for {bruker} ({rolle}): ').strip()
        tok = _skjemafelt(html2, 'csrfmiddlewaretoken') or tok
        st, h, html = k.kall('/accounts/login/', 'POST', data={
            'csrfmiddlewaretoken': tok or '', 'totp_code': kode, 'next': '/'}, csrf=True)
        st2, h2, html2 = k.kall('/accounts/login/')
    if 'mfa_setup' in html2 or 'Sett opp' in html2 and 'otpauth' in html2:
        r.hopp(f'{rolle}: kontoen må først sette opp MFA i nettleseren')
        return False
    st, h, _ = k.kall('/min-profil/')
    if st != 200:
        r.feil(f'{rolle}: innlogging feilet (min-profil svarte {st}) — feil passord, låst konto, eller må bytte passord')
        return False
    sesjon_etter = k.cookie('sessionid')
    r.sjekk(sesjon_for != sesjon_etter, f'{rolle}: ny sesjons-ID etter innlogging (ingen sesjonsfiksering)',
            f'{rolle}: sessionid er den samme før og etter innlogging')
    r.ok(f'{rolle}: innlogget som {bruker}')
    return True


# ── Testene ───────────────────────────────────────────────────────────────────

def test_transport(base, r):
    r.overskrift('Transport og hoder')
    u = urllib.parse.urlparse(base)
    k = Klient(base)
    if u.scheme == 'https':
        try:
            st, h, _ = Klient('http://' + u.netloc).kall('/healthz/')
            r.sjekk(st in (301, 302, 307, 308) and (h.get('location') or '').startswith('https://'),
                    f'http:// omdirigeres til https:// ({st})', f'http:// svarte {st} uten omdirigering til https')
        except Exception as e:   # noqa: BLE001
            r.info(f'http:// ble ikke nådd ({e.__class__.__name__}) — porten er trolig stengt, som er greit')
    st, h, html = k.kall('/accounts/login/')
    r.sjekk(st == 200, f'/accounts/login/ svarer {st}')
    lav = h
    hsts = lav.get('strict-transport-security', '')
    r.sjekk('max-age=' in hsts and int(re.search(r'max-age=(\d+)', hsts or 'max-age=0').group(1)) >= 15552000,
            f'HSTS: {hsts or "mangler"}', f'HSTS mangler eller er for kort: {hsts or "mangler"}')
    csp = lav.get('content-security-policy', '')
    r.sjekk(bool(csp), f'CSP satt ({len(csp)} tegn)', 'Content-Security-Policy mangler')
    if csp:
        r.sjekk("'unsafe-inline'" not in csp.split('script-src')[-1].split(';')[0] if 'script-src' in csp else True,
                'CSP script-src uten unsafe-inline', 'CSP script-src tillater unsafe-inline')
        r.sjekk("'unsafe-eval'" not in csp, 'CSP uten unsafe-eval', 'CSP tillater unsafe-eval')
        r.sjekk('nonce-' in csp, 'CSP bruker nonce', 'CSP uten nonce (inline-script må da være hvitelistet på annen måte)')
        r.info(f'CSP: {csp[:400]}')
    r.sjekk(lav.get('x-content-type-options', '').lower() == 'nosniff', 'X-Content-Type-Options: nosniff',
            'X-Content-Type-Options mangler')
    xfo = lav.get('x-frame-options', '').upper()
    r.sjekk(xfo in ('DENY', 'SAMEORIGIN') or 'frame-ancestors' in csp, f'Rammesperre: X-Frame-Options {xfo or "-"}',
            'Verken X-Frame-Options eller frame-ancestors')
    rp = lav.get('referrer-policy', '')
    r.sjekk(rp and rp != 'unsafe-url', f'Referrer-Policy: {rp}', 'Referrer-Policy mangler')
    pp = lav.get('permissions-policy', '')
    (r.ok if pp else r.info)(f'Permissions-Policy: {pp or "mangler (lav prioritet)"}')
    srv = lav.get('server', '')
    r.sjekk(not re.search(r'\d', srv), f'Server-hodet uten versjon ({srv or "tomt"})', f'Server-hodet lekker versjon: {srv}')
    cc = lav.get('cache-control', '')
    r.sjekk('no-store' in cc or 'no-cache' in cc or 'private' in cc, f'Innloggingssiden cacher ikke ({cc})',
            f'Innloggingssiden mangler Cache-Control no-store/private ({cc or "tomt"})')
    r.sjekk('Traceback' not in html and 'DEBUG = True' not in html, 'Innloggingssiden uten debug-spor')
    return k


def test_cookies(k, r, etter_innlogging=False):
    r.overskrift('Cookies' + (' etter innlogging' if etter_innlogging else ' før innlogging'))
    for navn in (['csrftoken'] + (['sessionid'] if etter_innlogging else [])):
        c = k.cookieobj(navn)
        if c is None:
            r.feil(f'{navn}: ikke satt') if navn == 'sessionid' else r.info(f'{navn}: ikke satt ennå')
            continue
        r.sjekk(c.secure, f'{navn}: Secure', f'{navn}: mangler Secure')
        httponly = 'httponly' in {x.lower() for x in c._rest}
        if navn == 'sessionid':
            r.sjekk(httponly, 'sessionid: HttpOnly', 'sessionid: mangler HttpOnly')
        else:
            r.sjekk(httponly, 'csrftoken: HttpOnly (portalen leser tokenet fra skjemaet)',
                    'csrftoken: uten HttpOnly — greit om det er med vilje')
        ss = {x.lower(): v for x, v in c._rest.items()}.get('samesite', '')
        r.sjekk(ss.lower() in ('lax', 'strict'), f'{navn}: SameSite={ss}', f'{navn}: SameSite mangler eller er None')


def test_stengt(base, r):
    r.overskrift('Uten innlogging: alt skal være stengt')
    k = Klient(base)
    for sti in STENGT_GET:
        st, h, html = k.kall(sti)
        loc = h.get('location', '')
        ok = st in (401, 403, 404, 405) or (st in (301, 302) and '/accounts/login/' in loc)
        if st == 200 and sti == '/':
            ok = False
        if ok:
            continue
        r.feil(f'GET {sti} svarte {st} {loc} uten innlogging')
    r.ok(f'{len(STENGT_GET)} sider og API-er sjekket — de som ikke står som FEIL over, er stengt')
    for sti in STENGT_POST:
        st, h, html = k.kall(sti, 'POST', json_data={})
        loc = h.get('location', '')
        ok = st in (401, 403, 404, 405) or (st in (301, 302) and '/accounts/login/' in loc)
        if not ok:
            r.feil(f'POST {sti} uten innlogging og CSRF svarte {st}')
        elif st == 500:
            r.feil(f'POST {sti} ga 500')
    r.ok(f'{len(STENGT_POST)} skriveendepunkter avviser POST uten innlogging/CSRF')
    r.overskrift('Åpne sider og ting som ikke skal finnes')
    for sti in AAPENT:
        st, h, html = k.kall(sti)
        r.sjekk(st == 200, f'GET {sti} → {st}', f'GET {sti} → {st} (forventet 200)')
        if sti == '/healthz/':
            r.sjekk(len(html) < 300 and 'Traceback' not in html, f'/healthz/ er kort ({len(html)} tegn): {html.strip()[:80]!r}',
                    f'/healthz/ er lang ({len(html)} tegn) — lekker den noe?')
        if sti == '/vaktliste/sw.js':
            r.sjekk('javascript' in h.get('content-type', ''), 'sw.js serveres som JavaScript')
    for sti in FINNES_IKKE:
        st, h, html = k.kall(sti)
        r.sjekk(st in (404, 403, 301, 302) and 'Traceback' not in html, f'GET {sti} → {st}',
                f'GET {sti} → {st} — finnes!')
    st, h, html = k.kall('/finnes-ikke-' + ''.join(random.choices(string.ascii_lowercase, k=8)) + '/')
    r.sjekk(st == 404 and 'Traceback' not in html and 'URLconf' not in html,
            'Ukjent side gir egen 404 uten URL-liste', f'Ukjent side: {st}, og siden røper Djangos URLconf/traceback')


def test_csrf_og_ratelimit(base, r):
    r.overskrift('CSRF og rate-limiting på innlogging')
    k = Klient(base)
    st, h, _ = k.kall('/accounts/login/', 'POST', data={'username': 'x', 'password': 'y'})
    r.sjekk(st == 403, f'POST innlogging uten CSRF-token → {st}', f'POST innlogging uten CSRF-token → {st} (forventet 403)')
    k = Klient(base)
    st, h, html = k.kall('/accounts/login/')
    tok = _skjemafelt(html, 'csrfmiddlewaretoken')
    bruker = 'finnesikke-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    koder = []
    for i in range(12):
        st, h, html = k.kall('/accounts/login/', 'POST', data={
            'csrfmiddlewaretoken': tok, 'username': bruker, 'password': 'feil-' + str(i)}, csrf=True)
        koder.append(st)
        if st == 429:
            break
    r.sjekk(429 in koder, f'Rate-limit slår inn etter {koder.index(429) if 429 in koder else "-"} feilede forsøk (grensen er 10/5 min per brukernavn)',
            f'Ingen 429 etter {len(koder)} feilede innlogginger: {koder} — RATELIMIT_ENABLE er av, eller cachen svarer ikke')
    feil_html = [x for x in koder if x not in (429,)]
    r.info(f'Svarkoder på feil passord: {sorted(set(feil_html))}')
    # Brukernavn-enumerering: ukjent bruker og feil passord skal gi samme melding.
    k2 = Klient(base)
    st, h, html = k2.kall('/accounts/login/')
    tok2 = _skjemafelt(html, 'csrfmiddlewaretoken')
    st1, _, html1 = k2.kall('/accounts/login/', 'POST', data={'csrfmiddlewaretoken': tok2, 'username': 'finnesikke-zz', 'password': 'x'}, csrf=True)
    m1 = re.search(r'class="alert alert-danger">(.*?)</div>', html1, re.S)
    tekst = re.sub(r'<[^>]+>', '', m1.group(1)).strip() if m1 else '(ikke funnet i HTML)'
    r.info(f'Feilmelding ved ukjent bruker: {tekst!r} — sjekk at feil passord på en ekte konto gir samme tekst')


def test_roller(base, r, admin, leser, enhet):
    r.overskrift('Rollegrenser')
    ka = kl = ke = None
    if leser:
        kl = Klient(base)
        if logg_inn(kl, r, leser, getpass.getpass(f'  Passord for {leser} (leser): '), 'leser'):
            test_cookies(kl, r, etter_innlogging=True)
            for sti in ADMIN_SIDER:
                st, h, _ = kl.kall(sti)
                r.sjekk(st == 403, f'leser: GET {sti} → {st}', f'leser: GET {sti} → {st} (forventet 403)')
            st, h, html = kl.kall('/pasienter/api/patients/', 'POST', json_data={'navn': 'Test'}, csrf=True)
            r.sjekk(st == 403, f'leser: POST ny pasient → {st}', f'leser: POST ny pasient → {st} (forventet 403)')
            st, h, html = kl.kall('/vaktliste/api/korps/', 'POST', json_data={'navn': 'Testkorps'}, csrf=True)
            r.sjekk(st == 403, f'leser: POST nytt korps → {st}', f'leser: POST nytt korps → {st} (forventet 403)')
            st, h, html = kl.kall('/oppdrag/api/lokasjoner/', 'POST', json_data={'navn': 'Test'}, csrf=True)
            r.sjekk(st == 403, f'leser: POST ny lokasjon → {st}', f'leser: POST ny lokasjon → {st} (forventet 403)')
            st, h, html = kl.kall('/portal-admin/brukere/1/', 'POST', data={'role': 'admin'}, csrf=True)
            r.sjekk(st in (403, 405), f'leser: POST endre bruker → {st}', f'leser: POST endre bruker → {st} (forventet 403)')
            for sti in ('/pasienter/api/patients/', '/oppdrag/api/oppdrag/', '/vaktliste/api/vaktlister/'):
                st, h, _ = kl.kall(sti)
                r.info(f'leser: GET {sti} → {st} (200 = har les på modulen, 403 = har ikke)')
            gammel = kl.cookie('sessionid')
            st, h, html = kl.kall('/accounts/logout/', 'POST', data={'csrfmiddlewaretoken': kl.cookie('csrftoken') or ''}, csrf=True)
            r.sjekk(st in (302, 200), f'leser: POST logout → {st}')
            st, h, _ = kl.kall('/accounts/logout/')
            r.sjekk(st in (405, 302, 403), f'leser: GET logout → {st} (utlogging skal kreve POST)',
                    f'leser: GET logout → {st} — utlogging via GET er CSRF-utsatt')
            k3 = Klient(base); k3.sett_cookie('sessionid', gammel or 'x')
            st, h, _ = k3.kall('/min-profil/')
            r.sjekk(st != 200, 'leser: gammel sesjons-ID virker ikke etter utlogging',
                    'leser: gammel sesjons-ID gir fortsatt 200 etter utlogging')
    if enhet:
        ke = Klient(base)
        if logg_inn(ke, r, enhet, getpass.getpass(f'  Passord for {enhet} (enhetskonto): '), 'enhet'):
            st, h, html = ke.kall('/oppdrag/')
            r.sjekk(st == 200 and 'oppdrag-enhet' in html, f'enhet: /oppdrag/ gir enhetsskjermen ({st})',
                    f'enhet: /oppdrag/ → {st}, og ikke enhetsskjermen')
            for sti in ('/oppdrag/api/lokasjoner/', '/oppdrag/api/enhetstyper/', '/oppdrag/api/problemstillinger/'):
                st, h, _ = ke.kall(sti, 'POST', json_data={'navn': 'Test'}, csrf=True)
                r.sjekk(st == 403, f'enhet: POST {sti} → {st}', f'enhet: POST {sti} → {st} (forventet 403)')
            st, h, _ = ke.kall('/oppdrag/api/bilinnstillinger/', 'PUT', json_data={}, csrf=True)
            r.sjekk(st == 403, f'enhet: PUT bilinnstillinger → {st}', f'enhet: PUT bilinnstillinger → {st} (forventet 403)')
            for sti in ADMIN_SIDER[:3]:
                st, h, _ = ke.kall(sti)
                r.sjekk(st == 403, f'enhet: GET {sti} → {st}', f'enhet: GET {sti} → {st} (forventet 403)')
    if admin:
        ka = Klient(base)
        if logg_inn(ka, r, admin, getpass.getpass(f'  Passord for {admin} (admin): '), 'admin'):
            for sti in ADMIN_SIDER:
                st, h, _ = ka.kall(sti)
                r.sjekk(st == 200, f'admin: GET {sti} → {st}', f'admin: GET {sti} → {st} (forventet 200)')
            st, h, html = ka.kall('/portal-admin/server-status/json/')
            try:
                d = json.loads(html)
                rader = {x['nokkel']: x for x in d.get('konfig', {}).get('rader', [])}
                for n, rad in rader.items():
                    (r.ok if rad['ok'] else r.feil)(f'konfigsjekk: {n} = {rad["verdi"]}')
            except Exception as e:   # noqa: BLE001
                r.info(f'admin: kunne ikke lese konfigsjekken ({e})')
            st, h, html = ka.kall('/portal-admin/backup/patients/last-ned/999999/')
            r.sjekk(st == 404, f'admin: nedlasting av ukjent backup → {st}', f'admin: nedlasting av ukjent backup → {st}')
            st, h, html = ka.kall('/portal-admin/auditlog/eksport.csv?q=%3Dcmd%7C')
            r.sjekk(st == 200, f'admin: audit-eksport svarer {st}')
    if not (admin or leser or enhet):
        r.hopp('Ingen kontoer oppgitt — rollegrensene er ikke testet (bruk --admin/--leser/--enhet)')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('url', help='f.eks. https://testportal.sanitet.net')
    p.add_argument('--admin', help='brukernavn for en global admin')
    p.add_argument('--leser', help='brukernavn for en bruker med bare les-tilgang')
    p.add_argument('--enhet', help='brukernavn for en enhetskonto (koblet til en Enhet i oppdrag)')
    p.add_argument('--uten-ratelimit', action='store_true', help='hopp over de 12 feilede innloggingene')
    a = p.parse_args()
    base = a.url.rstrip('/')
    r = Rapport()
    print(f'Sikkerhetssjekk av {base}\n')
    try:
        k = test_transport(base, r)
        test_cookies(k, r)
        test_stengt(base, r)
        if a.uten_ratelimit:
            r.hopp('Rate-limit-testen hoppet over')
        else:
            test_csrf_og_ratelimit(base, r)
        test_roller(base, r, a.admin, a.leser, a.enhet)
    except KeyboardInterrupt:
        r.info('Avbrutt')
    print(f'\nResultat: {r.antall["OK"]} OK, {r.antall["FEIL"]} FEIL, {r.antall["INFO"]} info, {r.antall["HOPP"]} hoppet over')
    print('Lim inn hele utskriften over i chatten.')
    return 1 if r.antall['FEIL'] else 0


if __name__ == '__main__':
    sys.exit(main())
