from django.test import TestCase, override_settings
from django.urls import reverse
from .test_business import BusinessData
from .models import RestaurantInfo, AttendanceLocationPolicy


class LocationAdminPolicyTests(BusinessData, TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()

    def setUp(self):
        self.info=RestaurantInfo.objects.create(name='Test',address='Original',opening_time='08:00',closing_time='23:00',latitude=10,longitude=106)
        self.policy=AttendanceLocationPolicy.objects.create(restaurant=self.info)
        self.data={'latitude':'11','longitude':'107','address':'Intentional test edit','attendance_radius_m':150,'max_accuracy_m':50,'mode':'FACE_AND_GPS','is_active':'on'}

    def test_manager_and_staff_cannot_read_or_write_admin_settings(self):
        for user in (self.manager,self.staff,self.customer):
            self.client.force_login(user)
            self.assertEqual(self.client.get('/management/settings/location/').status_code,404)
            self.assertEqual(self.client.post('/management/settings/location/',self.data).status_code,404)
        self.info.refresh_from_db();self.assertEqual(float(self.info.latitude),10)
        self.assertTrue(AttendanceLocationPolicy.objects.filter(pk=self.policy.pk).exists())

    @override_settings(DEBUG=False,SECURE_SSL_REDIRECT=False)
    def test_map_worker_served_by_production_static_middleware(self):
        from django.contrib.staticfiles import finders
        for name in ('vendor/maplibre/maplibre-gl-worker.js','vendor/leaflet/leaflet.js','location/maps.js'):
            self.assertIsNone(finders.find(name))

    def test_admin_must_explicitly_confirm_and_get_never_changes_location(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/management/settings/location/').status_code,404)
        self.assertEqual(self.client.post('/management/settings/location/',{**self.data,'confirm_location_change':'on'}).status_code,404)
        self.info.refresh_from_db();self.assertEqual(float(self.info.latitude),10)
        self.policy.refresh_from_db();self.assertEqual(self.policy.attendance_radius_m,150)

    def test_keyless_map_assets_and_worker_are_local_and_pinned(self):
        from pathlib import Path
        from django.conf import settings
        from .models import AttendanceLocationEvent
        for name in ('leaflet','maplibre'):
            self.assertFalse((Path(settings.BASE_DIR)/'static/vendor'/name).exists())
        self.assertEqual(AttendanceLocationEvent._meta.db_table,'customers_attendancelocationevent')
        self.assertFalse(AttendanceLocationEvent.objects.exists())
