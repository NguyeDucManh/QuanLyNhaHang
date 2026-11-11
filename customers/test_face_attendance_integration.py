"""Real HTTP/challenge/DB/GPS/punch flow; only biometric inference is mocked."""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from django.test import TestCase, override_settings
from django.urls import reverse
from .test_module07 import Module07Fixtures
from .models import FaceProfile, FaceEmbedding, RestaurantInfo, AttendanceLocationPolicy, Attendance, WorkSchedule


@override_settings(FACEID_REQUIRE_LIVENESS=False, FACEID_DEFAULT_THRESHOLD=.8)
class FaceAttendanceIntegrationTests(Module07Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.initialize()

    def setUp(self):
        self.personnel()
        self.schedule_row = self.approved_schedule()
        profile = FaceProfile.objects.create(employee=self.employee, model_version='test-only')
        FaceEmbedding.objects.create(profile=profile, vector=[1., 0.], image_hash='test-only')
        restaurant = RestaurantInfo.objects.create(name='Test only', address='Test',
            opening_time='08:00', closing_time='23:00', latitude=10, longitude=106)
        AttendanceLocationPolicy.objects.create(restaurant=restaurant, mode='FACE_AND_GPS')
        self.client.force_login(self.staff)
        self.net = SimpleNamespace(model_version='test-only', process=lambda frame:
            (np.array([1., 0.]), {'yaw': 0, 'blink': 0}, frame))

    def attempt(self, action, point):
        challenge = self.client.post(reverse('face_challenge'), '{}', content_type='application/json')
        self.assertEqual(challenge.status_code, 200)
        return self.client.post(reverse('secure_attendance'), json.dumps({
            'challenge': challenge.json()['id'], 'frames': ['a','b','c','d','e'],
            'schedule': self.schedule_row.pk, 'action': action, 'location': point}), content_type='application/json')

    def test_face_and_gps_check_in_and_out_use_existing_punch_service(self):
        with patch('customers.ai.face.face_enrollment_service.engine', return_value=self.net):
            with patch('django.utils.timezone.now', return_value=self.schedule_row.start_at):
                response = self.attempt('in', {'latitude':10, 'longitude':106, 'accuracy':5})
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()['face']['similarity'], 1.)
            with patch('django.utils.timezone.now', return_value=self.schedule_row.end_at):
                response = self.attempt('out', {'latitude':10, 'longitude':106, 'accuracy':5})
                self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Attendance.objects.count(), 1)
        row = Attendance.objects.get()
        self.assertEqual(row.check_in_time, self.schedule_row.start_at)
        self.assertEqual(row.check_out_time, self.schedule_row.end_at)

    def test_outside_gps_and_nonmatching_face_never_write_attendance(self):
        with patch('customers.ai.face.face_enrollment_service.engine', return_value=self.net):
            self.assertEqual(self.attempt('in', {'latitude':11, 'longitude':106, 'accuracy':5}).status_code, 400)
            self.net.process = lambda frame: (np.array([0., 1.]), {'yaw':0}, frame)
            self.assertEqual(self.attempt('in', {'latitude':10, 'longitude':106, 'accuracy':5}).status_code, 400)
        self.assertFalse(Attendance.objects.exists())

    def test_location_marker_urls_use_static_paths(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('location_settings'))
        self.assertEqual(response.status_code, 200)
        for name in ('marker-icon.png', 'marker-icon-2x.png', 'marker-shadow.png'):
            self.assertContains(response, '/static/vendor/leaflet/images/' + name)


@override_settings(FACEID_REQUIRE_LIVENESS=False, FACEID_DEFAULT_THRESHOLD=.8)
class FaceWorkflowHTTPTests(Module07Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.initialize()

    def test_admin_setup_enroll_approve_then_staff_authenticate_and_punch(self):
        self.personnel()
        restaurant=RestaurantInfo.objects.create(name='Test workflow',address='Test only',opening_time='08:00',closing_time='23:00')
        # Test-only passwords: never touches the production users.
        for user in (self.admin,self.staff):
            user.set_password('Workflow-test-only-2026!');user.save(update_fields=['password'])
        self.assertTrue(self.client.login(username=self.admin.username,password='Workflow-test-only-2026!'))
        response=self.client.post(reverse('location_settings'),{'confirm_location_change':'on','latitude':'10','longitude':'106','address':'Test workflow address','attendance_radius_m':150,'max_accuracy_m':50,'mode':'FACE_AND_GPS','is_active':'on'})
        self.assertEqual(response.status_code,302)
        restaurant.refresh_from_db();self.assertEqual(float(restaurant.latitude),10)
        net=SimpleNamespace(model_version='test-workflow',process=lambda frame:(np.array([1.,0.]),{'yaw':0,'blink':0},frame))
        with patch('customers.ai.face.face_enrollment_service.engine',return_value=net):
            response=self.client.post(reverse('face_enrollment',args=[self.employee.pk]),json.dumps({'consent':True,'frames':[str(n) for n in range(15)]}),content_type='application/json')
            self.assertEqual(response.status_code,200,response.content)
            self.assertEqual(response.json()['samples'],15)
            response=self.client.post(reverse('module07_add',args=['workschedule']),{'employee':self.employee.pk,'shift':self.shift.pk,'work_date':str(self.day),'note':'Test workflow'})
            self.assertEqual(response.status_code,302,response.content)
            schedule=WorkSchedule.objects.get(employee=self.employee)
            self.assertEqual(schedule.status,'DRAFT')
            from django.test import Client
            staff_client=Client()
            self.assertTrue(staff_client.login(username=self.staff.username,password='Workflow-test-only-2026!'))
            with patch('django.utils.timezone.now',return_value=schedule.start_at):
                self.assertEqual(staff_client.get(reverse('attendance_status')).json()['schedule_status'],'UNAPPROVED')
                challenge=staff_client.post(reverse('face_challenge'),'{}',content_type='application/json').json()
                denied=staff_client.post(reverse('secure_attendance'),json.dumps({'schedule':schedule.pk,'action':'in','challenge':challenge['id'],'frames':['a','b','c','d','e'],'location':{'latitude':10,'longitude':106,'accuracy':5}}),content_type='application/json')
                self.assertEqual(denied.status_code,400)
                self.assertFalse(Attendance.objects.exists())
            response=self.client.post(reverse('module07_state',args=['workschedule',schedule.pk]),{'state':'APPROVED'})
            self.assertEqual(response.status_code,302)
            schedule.refresh_from_db();self.assertEqual(schedule.status,'APPROVED')
            self.client.logout()
            self.assertTrue(self.client.login(username=self.staff.username,password='Workflow-test-only-2026!'))
            for action,now in [('in',schedule.start_at),('out',schedule.end_at)]:
                with patch('django.utils.timezone.now',return_value=now):
                    readiness=self.client.get(reverse('attendance_status'))
                    self.assertEqual(readiness.json()['schedule_status'],'AVAILABLE')
                    challenge=self.client.post(reverse('face_challenge'),'{}',content_type='application/json').json()
                    response=self.client.post(reverse('secure_attendance'),json.dumps({'schedule':schedule.pk,'action':action,'challenge':challenge['id'],'frames':['a','b','c','d','e'],'location':{'latitude':10,'longitude':106,'accuracy':5}}),content_type='application/json')
                    self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(Attendance.objects.count(),1)
        row=Attendance.objects.get();self.assertEqual(row.check_in_time,schedule.start_at);self.assertEqual(row.check_out_time,schedule.end_at)
