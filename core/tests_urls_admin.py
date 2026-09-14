"""Adminflaten: hele kartet under `/portal-admin/`, låst til literale verdier.

Rutene lå spredt på `myproject/urls.py`, `core/urls.py` og `accounts/urls.py`
fram til 14. sep. 2026, og ble samlet i `core/urls_admin.py` (gjeldspunkt 3.2).

**Testen låser kartet fordi feilen den fanger er en brukeren møter, ikke en
utvikleren gjør.** En `{% url %}` som slutter å virke gir 500 på en side som
virket i går; en sti som flytter gjør et bokmerke til en 404. Verken suiten
eller `manage.py check` sier noe om det — så lenge *en* rute svarer på navnet,
er alle fornøyde.

At kartet står skrevet her, er også den eneste måten å se at samlingen ikke
endret noe: den ble gjort ved å flytte linjer, og en flyttet linje som mistet
en skråstrek ser lik ut.
"""
from __future__ import annotations

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import get_resolver

#: Sti → navn, nøyaktig som før samlingen. Endres en rad her, skal det være
#: fordi noen har bestemt at adressen skal endres — ikke fordi en refaktorering
#: tok den med seg.
KARTET = {
    'portal-admin/auditlog/': 'audit_log_list',
    'portal-admin/auditlog/eksport.csv': 'audit_log_csv_export',
    'portal-admin/backup/': 'backup_admin',
    'portal-admin/backup/<slug:slug>/restore/<int:pk>/': 'backup_admin_restore',
    'portal-admin/backup/<slug:slug>/slett/<int:pk>/': 'backup_admin_delete',
    'portal-admin/backup/kjor/': 'backup_admin_run_alle',
    'portal-admin/backup/kjor/<slug:slug>/': 'backup_admin_run',
    'portal-admin/backup/plan/<slug:slug>/': 'backup_admin_plan',
    'portal-admin/brukere/': 'user_list',
    'portal-admin/brukere/<int:pk>/': 'user_detail',
    'portal-admin/brukere/<int:pk>/slett/': 'user_delete',
    'portal-admin/brukere/ny/': 'user_create',
    'portal-admin/innloggingslogg/': 'login_event_list',
    'portal-admin/innstillinger/': 'portal_settings',
    'portal-admin/moduler/': 'module_admin_list',
    'portal-admin/moduler/<slug:slug>/': 'module_admin_edit',
    'portal-admin/server-status/': 'admin_server_status',
    'portal-admin/server-status/json/': 'admin_server_status_json',
    'portal-admin/server-status/sessions/': 'admin_sessions_list',
    'portal-admin/server-status/sessions/kill-all/': 'admin_session_kill_all',
    'portal-admin/server-status/sessions/kill/': 'admin_session_kill',
}


def _alle_ruter(resolver=None, prefiks=''):
    resolver = resolver or get_resolver()
    ut = []
    for p in resolver.url_patterns:
        if hasattr(p, 'url_patterns'):
            ut += _alle_ruter(p, prefiks + str(p.pattern))
        else:
            ut.append((prefiks + str(p.pattern), p.name))
    return ut


class PortalAdminKartetTests(SimpleTestCase):

    def test_stiene_og_navnene_er_uendret(self) -> None:
        funnet = {sti: navn for sti, navn in _alle_ruter()
                  if sti.startswith('portal-admin/')}
        self.assertEqual(funnet, KARTET)

    def test_hele_flaten_har_ett_navnerom(self) -> None:
        """Rutene lå i to apper med hver sin `app_name`, så det samme
        skjermbildet het `accounts:user_list` eller `core:backup_admin`
        avhengig av hvilken app som tilfeldigvis eide viewet.

        **Og navnerommet er det snapshotet mitt ikke så.** Da rutene ble
        samlet, sammenlignet jeg `pattern.name` — som er navnet *uten*
        navnerom — og fikk «identisk kart» mens hver `{% url 'accounts:…' %}`
        i malene var død. Viewtestene fanget det. Derfor står navnerommet her.
        """
        from django.urls import reverse

        for navn in sorted(set(KARTET.values())):
            with self.subTest(navn=navn):
                try:
                    reverse(f'portaladmin:{navn}')
                except Exception as feil:   # noqa: BLE001
                    self.assertNotIn('not a valid view function or pattern name',
                                     str(feil), f'portaladmin:{navn} finnes ikke')

    def test_alle_ligger_i_en_fil(self) -> None:
        """Poenget med samlingen. Står en rute et annet sted, er flaten delt
        igjen — og neste som leter finner bare halvparten."""
        from core import urls_admin

        i_fila = {'portal-admin/' + str(p.pattern) for p in urls_admin.urlpatterns}
        self.assertEqual(i_fila, set(KARTET))

    def test_ingen_andre_filer_ruter_under_portal_admin(self) -> None:
        from pathlib import Path

        from django.conf import settings

        funn = []
        for navn in ('myproject/urls.py', 'core/urls.py', 'accounts/urls.py',
                     'patients/urls.py'):
            tekst = Path(settings.BASE_DIR, navn).read_text(encoding='utf-8')
            for linje in tekst.split('\n'):
                ren = linje.strip()
                if ren.startswith(('path(', 're_path(')) and 'portal-admin/' in ren:
                    # `include`-linja i prosjektet er selve samlingen.
                    if 'core.urls_admin' in ren:
                        continue
                    funn.append(f'{navn}: {ren}')
        self.assertEqual(funn, [], (
            'Ruter under /portal-admin/ utenfor `core/urls_admin.py`:\n  '
            + '\n  '.join(funn)))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AdminsideneRendrerTests(TestCase):
    """Hver GET-side under `/portal-admin/` skal svare 200 for en global admin.

    `PortalAdminKartetTests` sier at ruta *finnes*; denne sier at siden
    *virker*. Det er to ulike spørsmål, og samlingen 14. sep. 2026 viste
    hvorfor: kartet så identisk ut mens hver `{% url 'accounts:…' %}` i malene
    var død, fordi navnerommet forsvant. Det ble fanget av tre viewtester som
    tilfeldigvis rendret de riktige sidene.

    Her er det ingen tilfeldighet: lista er utledet av `KARTET`, så en ny
    adminside blir dekket i det øyeblikket ruta legges inn.
    """

    #: Ruter som tar argumenter, eller som ikke er GET. De dekkes av sine egne
    #: tester — poenget her er sidene man *navigerer* til.
    IKKE_GET = {
        'backup_admin_plan', 'backup_admin_run', 'backup_admin_run_alle',
        'backup_admin_restore', 'backup_admin_delete',
        'module_admin_edit', 'user_detail', 'user_delete',
        'admin_sessions_list', 'admin_session_kill', 'admin_session_kill_all',
        'admin_server_status_json', 'audit_log_csv_export',
    }

    def setUp(self) -> None:
        from accounts.models import CustomUser
        from accounts.test_helpers import gi_standardtilgang

        self.admin = CustomUser.objects.create_user(
            username='sideadmin', password='pwd', role='admin',
            must_change_password=False)
        gi_standardtilgang(self.admin, 'admin')
        self.client.force_login(self.admin)

    def test_alle_get_sider_svarer_200(self) -> None:
        from django.urls import reverse

        prövd = []
        for sti, navn in sorted(KARTET.items()):
            if navn in self.IKKE_GET:
                continue
            with self.subTest(side=navn):
                url = reverse(f'portaladmin:{navn}')
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200,
                                 f'{url} ga {resp.status_code}')
                prövd.append(navn)
        self.assertGreaterEqual(len(prövd), 6, f'prøvde bare {prövd}')
