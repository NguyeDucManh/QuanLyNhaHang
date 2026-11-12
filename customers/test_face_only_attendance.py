import json
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from django.test import TestCase, override_settings
from django.utils import timezone
from .test_module07 import Module07Fixtures
from .models import FaceProfile, FaceEmbedding, Attendance, AttendanceLocationEvent


@override_settings(FACEID_REQUIRE_LIVENESS=False,FACEID_DEFAULT_THRESHOLD=.8)
class FaceOnlyAttendanceTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls):cls.initialize()
    def setUp(self):
        self.personnel();self.schedule_row=self.approved_schedule()
        profile=FaceProfile.objects.create(employee=self.employee,model_version='test')
        FaceEmbedding.objects.create(profile=profile,vector=[1.,0.],image_hash='test')
        self.net=SimpleNamespace(model_version='test',process=lambda frame:(np.array([1.,0.]),{'yaw':0,'blink':0},frame))
        self.client.force_login(self.staff)
    def attempt(self,action,**extra):
        challenge=self.client.post('/work/faceid/challenge/','{}',content_type='application/json').json()
        return self.client.post('/work/attendance/verify/',json.dumps({'schedule':self.schedule_row.pk,'action':action,
            'challenge':challenge['id'],'frames':['a','b','c','d','e'],**extra}),content_type='application/json')
    def test_in_out_without_restaurant_policy_or_coordinates_and_no_duplicate(self):
        with patch('django.utils.timezone.now',return_value=self.schedule_row.start_at),patch('customers.ai.face.face_enrollment_service.engine',return_value=self.net):
            with patch('django.utils.timezone.now',return_value=self.schedule_row.start_at):
                self.assertEqual(self.attempt('in').status_code,200)
                self.assertEqual(self.attempt('in').status_code,400)
            with patch('django.utils.timezone.now',return_value=self.schedule_row.end_at):
                self.assertEqual(self.attempt('out').status_code,200)
        self.assertEqual(Attendance.objects.count(),1)
        self.assertFalse(AttendanceLocationEvent.objects.exists())
    def test_nonmatching_face_and_unapproved_shift_never_write(self):
        self.net.process=lambda frame:(np.array([0.,1.]),{'yaw':0},frame)
        with patch('django.utils.timezone.now',return_value=self.schedule_row.start_at),patch('customers.ai.face.face_enrollment_service.engine',return_value=self.net):
            self.assertEqual(self.attempt('in').status_code,400)
        self.schedule_row.status='DRAFT';self.schedule_row.save()
        with patch('customers.ai.face.face_enrollment_service.verify_identity') as verify:
            self.assertEqual(self.attempt('in').status_code,400);verify.assert_not_called()
        self.assertFalse(Attendance.objects.exists())
    def test_location_payload_rejected_and_retired_endpoints_absent(self):
        self.assertEqual(self.attempt('in',location={'latitude':10,'longitude':106}).status_code,400)
        for path in ('/work/location/check/','/management/settings/location/'):
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertFalse(Attendance.objects.exists())
    def test_face_only_page_has_camera_but_no_location_resources(self):
        response=self.client.get('/work/faceid/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'data-face-realtime="attendance"')
        for value in ('navigator.geolocation','data-location-map','data-location-start','maplibre','leaflet'):
            self.assertNotContains(response,value)

    def test_busy_face_capacity_returns_retry_without_challenge_or_attendance_write(self):
        from .models import FaceChallenge
        before=FaceChallenge.objects.count()
        with patch('customers.ai.face.runtime._face_capacity.acquire',return_value=False):
            response=self.client.post('/work/attendance/verify/','{}',content_type='application/json')
        self.assertEqual(response.status_code,429);self.assertEqual(response.json()['code'],'FACE_BUSY')
        self.assertEqual(response['Retry-After'],'2')
        self.assertFalse(Attendance.objects.exists());self.assertEqual(FaceChallenge.objects.count(),before)
