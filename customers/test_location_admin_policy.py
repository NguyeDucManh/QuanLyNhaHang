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
        for user in (self.manager,self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('location_settings')).status_code,403)
            self.assertEqual(self.client.post(reverse('location_settings'),{**self.data,'confirm_location_change':'on'}).status_code,403)
            self.assertEqual(self.client.post(reverse('module07_edit',args=['restaurantinfo',self.info.pk]),self.data).status_code,403)
        self.info.refresh_from_db();self.assertEqual(float(self.info.latitude),10)

    @override_settings(DEBUG=False,SECURE_SSL_REDIRECT=False)
    def test_map_worker_served_by_production_static_middleware(self):
        response=self.client.get('/static/vendor/maplibre/maplibre-gl-worker.js',secure=True)
        self.assertEqual(response.status_code,200)
        self.assertIn('javascript',response['Content-Type'])

    def test_admin_must_explicitly_confirm_and_get_never_changes_location(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('location_settings')),'data-location-fields disabled')
        self.client.post(reverse('location_settings'),self.data)
        self.info.refresh_from_db();self.assertEqual(float(self.info.latitude),10)
        self.assertEqual(self.client.post(reverse('location_settings'),{**self.data,'confirm_location_change':'on'}).status_code,302)
        self.info.refresh_from_db();self.assertEqual(float(self.info.latitude),11)
        self.policy.refresh_from_db();self.assertEqual(self.policy.attendance_radius_m,150);self.assertEqual(self.policy.max_accuracy_m,50)

    def test_keyless_map_assets_and_worker_are_local_and_pinned(self):
        import hashlib,json
        from pathlib import Path
        from django.conf import settings
        root=Path(settings.BASE_DIR)/'static/vendor/maplibre'
        manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        for name,metadata in manifest['files'].items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),metadata['sha256'])
        self.client.force_login(self.admin)
        page=self.client.get(reverse('location_settings'))
        for name in ('maplibre-gl.js','maplibre-gl-worker.js','maplibre-gl.css','leaflet-maplibre-gl.js'):
            self.assertContains(page,'/static/vendor/maplibre/'+name)
        self.info.refresh_from_db();self.assertEqual(float(self.info.latitude),10)
