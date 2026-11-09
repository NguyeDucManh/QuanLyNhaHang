"""Regression contracts for static delivery and safe production fallbacks."""
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase, override_settings
from django.templatetags.static import static
from django.template.loader import render_to_string
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from customers.menu_service import serialize_item
import os
import runpy
from django.core.exceptions import ImproperlyConfigured


class EnvironmentProductionTests(SimpleTestCase):
    def configuration(self, **environment):
        values = {'DJANGO_SECRET_KEY': 'unit-test-configuration-only', 'DB_PASSWORD': 'unit-test-only'}
        values.update(environment)
        with patch.dict(os.environ, values, clear=True), patch('restaurant_system.environment.load_environment'):
            return runpy.run_module('restaurant_system.settings')

    def test_render_defaults_secure_and_preserves_postgresql(self):
        settings = self.configuration(RENDER='true')
        self.assertFalse(settings['DEBUG'])
        self.assertTrue(settings['SESSION_COOKIE_SECURE'])
        self.assertTrue(settings['SECURE_SSL_REDIRECT'])
        self.assertIn('https://smart-restaurant-demo.onrender.com', settings['CSRF_TRUSTED_ORIGINS'])
        self.assertEqual(settings['DATABASES']['default']['ENGINE'], 'django.db.backends.postgresql')

    def test_render_rejects_debug(self):
        with self.assertRaises(ImproperlyConfigured):
            self.configuration(RENDER='true', DJANGO_DEBUG='true')

    def test_database_url_without_legacy_password(self):
        with patch.dict(os.environ, {'DJANGO_SECRET_KEY': 'unit-test-only',
                'DATABASE_URL': 'postgresql://fixture:fixture@localhost/render_fixture'}, clear=True), patch('restaurant_system.environment.load_environment'):
            settings = runpy.run_module('restaurant_system.settings')
        self.assertEqual(settings['DATABASES']['default']['NAME'], 'render_fixture')

    def test_sqlite_url_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            self.configuration(DATABASE_URL='sqlite:///example.sqlite3')

    def test_test_database_cannot_equal_application_database(self):
        with self.assertRaises(ImproperlyConfigured):
            self.configuration(DB_NAME='fixture', DB_TEST_NAME='fixture')


class StaticDeliveryTests(TestCase):
    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=True)
    def test_production_assets_survive_middleware(self):
        # Requires collectstatic first; exercise the actual production backend.
        with override_settings(STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
        }):
            for path, mime in [
                ('customer/css/style.css', 'text/css'),
                ('customer/js/main.js', 'javascript'),
                ('ui/design-system.css', 'text/css'),
                ('ui/reference-match.css', 'text/css'),
                ('ui/images/garden-restaurant-hero.png', 'image/png'),
                ('ui/images/dish-placeholder.svg', 'image/svg+xml'),
                ('admin/css/style.css', 'text/css'),
                ('ui/staff-pos.css', 'text/css'),
            ]:
                with self.subTest(path=path):
                    response = self.client.get(static(path), secure=True)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(mime, response['Content-Type'])
                    self.assertIn('immutable', response['Cache-Control'])
                    self.assertTrue(b''.join(response.streaming_content))

    def test_missing_image_has_real_placeholder(self):
        for image in ['', 'missing/dish.png']:
            item = SimpleNamespace(pk=1, name='Món', category=SimpleNamespace(
                slug='mon', name='Món', is_active=True), price=1000,
                image=image, description='', is_available=True)
            self.assertIn('dish-placeholder', serialize_item(item)['image'])

    def test_svg_guard_and_vietnamese_booking_menu(self):
        request = RequestFactory().get('/menu/?from=booking')
        request.user = AnonymousUser()
        request.session = {}
        html = render_to_string('customer/menu.html', {
            'booking_menu': True, 'dishes': [], 'categories': []}, request=request)
        self.assertIn('Quay lại đặt bàn', html)
        self.assertNotIn('QUAY L?I', html)
        self.assertIn('width="0" height="0"', html)
        self.assertIn('svg.icon', html)

    @patch('restaurant_system.health.connection')
    def test_health_failure_does_not_leak_exception(self, connection):
        connection.cursor.side_effect = RuntimeError('private connection details')
        response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, 'private', status_code=503)


class HealthDatabaseTests(TestCase):
    def test_health_checks_real_test_database(self):
        self.assertJSONEqual(self.client.get('/healthz/').content, {'status': 'ok'})
