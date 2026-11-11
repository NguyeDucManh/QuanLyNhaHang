from django.test import TestCase
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

    def test_admin_must_explicitly_confirm_and_get_never_changes_location(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('location_settings')),'data-location-fields disabled')
        self.client.post(reverse('location_settings'),self.data)
        self.info.refresh_from_db();self.assertEqual(float(self.info.latitude),10)
        self.assertEqual(self.client.post(reverse('location_settings'),{**self.data,'confirm_location_change':'on'}).status_code,302)
        self.info.refresh_from_db();self.assertEqual(float(self.info.latitude),11)
        self.policy.refresh_from_db();self.assertEqual(self.policy.attendance_radius_m,150);self.assertEqual(self.policy.max_accuracy_m,50)
