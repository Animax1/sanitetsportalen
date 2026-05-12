"""Tester for Fase 5: varsel-API, endepunkt, og varselside.

Dekker:
- core.notifications.notify() — opprettelse + dedup
- /api/varsler/ulest-antall/ — autentisering + korrekt telling
- /varsler/ — paginering, vises kun for innlogget bruker
- /varsler/<pk>/lest/ — markerer som lest, redirecter til URL
- /varsler/marker-alle-lest/ — bulk-mark-as-read
- Sikkerhet: bruker kan ikke markere annen brukers varsel
"""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from core.models import Notification
from core.notifications import notify, DEDUP_WINDOW


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class NotifyApiTests(TestCase):
    """Enhets-tester for core.notifications.notify()."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='kari', password='pw12345678', must_change_password=False,
        )
        self.other = CustomUser.objects.create_user(
            username='ola', password='pw12345678', must_change_password=False,
        )

    def test_notify_creates_notification(self):
        n = notify(
            self.user, module_slug='patients', kind='patient_assigned',
            title='Tittel', message='Melding her', url='/pasienter/',
        )
        self.assertIsNotNone(n)
        self.assertEqual(n.user, self.user)
        self.assertEqual(n.module_slug, 'patients')
        self.assertEqual(n.kind, 'patient_assigned')
        self.assertEqual(n.level, Notification.LEVEL_INFO)
        self.assertFalse(n.is_read)

    def test_notify_dedup_within_24h(self):
        """Samme (user, kind, message) i 24t-vinduet skal ikke duplisere."""
        n1 = notify(self.user, module_slug='patients', kind='patient_assigned',
                    title='T', message='unik')
        n2 = notify(self.user, module_slug='patients', kind='patient_assigned',
                    title='T2', message='unik')
        self.assertIsNotNone(n1)
        self.assertIsNone(n2)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    def test_notify_no_dedup_for_different_users(self):
        """Andre bruker får varsel selv om kind+message matcher."""
        n1 = notify(self.user, module_slug='patients', kind='k', message='m')
        n2 = notify(self.other, module_slug='patients', kind='k', message='m')
        self.assertIsNotNone(n1)
        self.assertIsNotNone(n2)

    def test_notify_no_dedup_for_different_kind(self):
        n1 = notify(self.user, module_slug='patients', kind='assigned', message='m')
        n2 = notify(self.user, module_slug='patients', kind='transferred', message='m')
        self.assertIsNotNone(n1)
        self.assertIsNotNone(n2)

    def test_notify_outside_dedup_window_creates_new(self):
        """Varsel eldre enn 24t skal ikke blokkere."""
        n1 = notify(self.user, module_slug='patients', kind='k', message='m')
        # Sett created_at bakover
        Notification.objects.filter(pk=n1.pk).update(
            created_at=timezone.now() - DEDUP_WINDOW - timedelta(minutes=1),
        )
        n2 = notify(self.user, module_slug='patients', kind='k', message='m')
        self.assertIsNotNone(n2)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 2)

    def test_notify_anonymous_user_returns_none(self):
        from django.contrib.auth.models import AnonymousUser
        result = notify(AnonymousUser(), module_slug='patients', kind='k', message='m')
        self.assertIsNone(result)
        self.assertEqual(Notification.objects.count(), 0)

    def test_notify_none_user_returns_none(self):
        result = notify(None, module_slug='patients', kind='k', message='m')
        self.assertIsNone(result)

    def test_notify_with_level(self):
        n = notify(self.user, module_slug='patients', kind='k',
                   message='m', level=Notification.LEVEL_CRITICAL)
        self.assertEqual(n.level, Notification.LEVEL_CRITICAL)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class UnreadCountEndpointTests(TestCase):
    """Tester for /api/varsler/ulest-antall/."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='kari', password='pw12345678', must_change_password=False,
        )
        self.url = reverse('core:notification_unread_count')

    def test_requires_login(self):
        res = self.client.get(self.url)
        # @login_required redirecter til login
        self.assertIn(res.status_code, (302, 401, 403))

    def test_returns_zero_when_no_notifications(self):
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {'unread': 0})

    def test_counts_only_unread(self):
        notify(self.user, module_slug='p', kind='k1', message='a')
        notify(self.user, module_slug='p', kind='k2', message='b')
        # Marker en som lest
        Notification.objects.filter(user=self.user, kind='k1').update(is_read=True)
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertEqual(res.json(), {'unread': 1})

    def test_counts_only_own_notifications(self):
        other = CustomUser.objects.create_user(
            username='ola', password='pw12345678', must_change_password=False,
        )
        notify(other, module_slug='p', kind='k', message='for ola')
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertEqual(res.json(), {'unread': 0})


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class NotificationListViewTests(TestCase):
    """Tester for /varsler/-siden."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='kari', password='pw12345678', must_change_password=False,
        )
        self.url = reverse('core:notification_list')

    def test_requires_login(self):
        res = self.client.get(self.url)
        self.assertIn(res.status_code, (302, 401, 403))

    def test_empty_list_renders_ok(self):
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Ingen varsler enda')

    def test_shows_only_own_notifications(self):
        other = CustomUser.objects.create_user(
            username='ola', password='pw12345678', must_change_password=False,
        )
        notify(self.user, module_slug='p', kind='k', title='Mitt', message='m1')
        notify(other, module_slug='p', kind='k', title='Hans', message='m2')
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertContains(res, 'Mitt')
        self.assertNotContains(res, 'Hans')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MarkReadTests(TestCase):
    """Tester for mark-as-read-endepunkter."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='kari', password='pw12345678', must_change_password=False,
        )
        self.other = CustomUser.objects.create_user(
            username='ola', password='pw12345678', must_change_password=False,
        )

    def test_mark_read_sets_is_read_and_redirects_to_url(self):
        n = notify(self.user, module_slug='p', kind='k', message='m',
                   url='/pasienter/?focus=42')
        self.client.force_login(self.user)
        res = self.client.get(reverse('core:notification_mark_read', args=[n.pk]))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/pasienter/?focus=42')
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        self.assertIsNotNone(n.read_at)

    def test_mark_read_redirects_to_list_when_no_url(self):
        n = notify(self.user, module_slug='p', kind='k', message='m', url='')
        self.client.force_login(self.user)
        res = self.client.get(reverse('core:notification_mark_read', args=[n.pk]))
        self.assertEqual(res.status_code, 302)
        self.assertIn('/varsler/', res.url)

    def test_mark_read_cannot_touch_other_users_notification(self):
        n = notify(self.other, module_slug='p', kind='k', message='m')
        self.client.force_login(self.user)
        res = self.client.get(reverse('core:notification_mark_read', args=[n.pk]))
        self.assertEqual(res.status_code, 404)
        n.refresh_from_db()
        self.assertFalse(n.is_read)

    def test_mark_all_read_marks_only_own_unread(self):
        notify(self.user, module_slug='p', kind='k1', message='a')
        notify(self.user, module_slug='p', kind='k2', message='b')
        notify(self.other, module_slug='p', kind='k3', message='c')
        self.client.force_login(self.user)
        res = self.client.post(reverse('core:notification_mark_all_read'))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(
            Notification.objects.filter(user=self.user, is_read=False).count(),
            0,
        )
        # Andres varsler er urørt
        self.assertEqual(
            Notification.objects.filter(user=self.other, is_read=False).count(),
            1,
        )

    def test_mark_all_read_get_not_allowed(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse('core:notification_mark_all_read'))
        self.assertEqual(res.status_code, 405)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ContextProcessorTests(TestCase):
    """Tester for notification_unread_count context processor."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='kari', password='pw12345678', must_change_password=False,
        )

    def test_authenticated_sees_count_in_context(self):
        notify(self.user, module_slug='p', kind='k', message='m')
        self.client.force_login(self.user)
        # Bruker dashboard-siden (bruker base_portal.html)
        res = self.client.get(reverse('core:portal_dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['notification_unread_count'], 1)

    def test_unauthenticated_gets_zero(self):
        # Hit en side som ikke krever login (login-siden bruker basis-template)
        from core.context_processors import notification_unread_count
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser
        req = RequestFactory().get('/')
        req.user = AnonymousUser()
        result = notification_unread_count(req)
        self.assertEqual(result, {'notification_unread_count': 0})
